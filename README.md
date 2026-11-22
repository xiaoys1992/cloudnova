# CloudNova — Revenue & Customer Q&A (Track B)

Ask plain-English questions about CloudNova's invoice ledger and get **trustworthy**
answers. This project cleans a messy ~5k-row invoice export into one well-defined
table, then lets you query it in natural language — every answer comes back **with
the exact SQL** that produced it, so finance can check the math. The business logic
(recognized revenue, MRR, churn, FX→USD) is specified once, up front, and the code
is generated to match.

## Run it

```bash
# 1. setup (Windows PowerShell; venv lives at .venv)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. add your Anthropic key
copy .env.example .env         # then edit .env:  ANTHROPIC_API_KEY=sk-ant-...

# 3. build the clean table + run the demo questions
.venv\Scripts\python -m app demo      # auto-runs `clean` if needed, then asks sample Qs

# 4. run the eval harness (expected/actual vs. an independent oracle)
.venv\Scripts\python -m evals
```

Other entry points: `python -m app clean` (build the table only),
`python -m app ask "<question>"` (one question), `python -m src.pipeline` (pipeline directly).

**Data flow:** raw CSV → cleaning pipeline (rules R01–R17) → `data/clean/cleaned.parquet`
+ `schema.json` → DuckDB view `invoices` → NL→SQL agent → answer + SQL.

## Architecture

Full write-up in [`docs/architecture.md`](./docs/architecture.md); the same diagram:

```mermaid
flowchart TD
    CSV[("data/raw/cloudnova_invoices.csv<br/>~5k dirty rows")]

    subgraph pipe["src/pipeline — Session A"]
        CLEAN["clean.py — rules R01..R17<br/>dedup, normalize categories/dates,<br/>FX to USD, derive mrr_usd"]
    end

    subgraph clean["data/clean — the only contract"]
        PARQ[("cleaned.parquet<br/>view: invoices")]
        SCHEMA[["schema.json<br/>columns, types, allowed_values, rules"]]
        REPORT["cleaning_report.md<br/>rows in/out, per-rule counts"]
    end

    DUCK{{"DuckDB — register parquet as view invoices"}}

    MSPEC["specs/metrics_spec.md"]
    FEWSHOT["src/agent/few_shots.yaml"]

    subgraph agent["src/agent — Session B"]
        PROMPT["prompt assembly<br/>schema.json + metrics_spec + few_shots"]
        SQLGEN["NL to SQL — LLM call"]
        GUARD["guardrails<br/>SELECT/WITH only, row cap, timeout"]
        EXEC["execute query<br/>retry once on SQL error"]
        ANSWER["answer — 2nd LLM call<br/>one paragraph quoting the numbers"]
    end

    CLI["app CLI<br/>python -m app clean | ask | demo"]

    subgraph eval["evals"]
        ORACLE["oracle.py<br/>independent pandas, no src imports"]
        HARNESS["harness — python -m evals<br/>compare vs tolerance"]
        RESULT{"PASS / FAIL / XFAIL"}
    end

    CSV --> CLEAN
    CLEAN --> PARQ
    CLEAN --> SCHEMA
    CLEAN --> REPORT

    PARQ --> DUCK
    SCHEMA --> PROMPT
    MSPEC --> PROMPT
    FEWSHOT --> PROMPT
    PROMPT --> SQLGEN --> GUARD --> EXEC --> ANSWER
    GUARD -. "reject: not read-only" .-> ANSWER
    DUCK --> EXEC

    CLI -- "clean" --> CLEAN
    CLI -- "ask / demo -> agent.ask()" --> PROMPT
    ANSWER --> CLI

    PARQ --> ORACLE
    ORACLE --> HARNESS
    HARNESS -- "agent.ask() per case" --> PROMPT
    ANSWER --> HARNESS
    HARNESS --> RESULT
```

## The specs (business logic lives here, not in code)

The build is **spec-first**: every spec was written and committed *before* the code
it governs. See [`/specs`](./specs):

- [`cleaning_spec.md`](./specs/cleaning_spec.md) — the cleaned schema, and every
  cleaning/normalization rule (R01–R17): dedup, categories, dates, FX→USD, MRR.
- [`metrics_spec.md`](./specs/metrics_spec.md) — what each metric *means* (recognized
  revenue, MRR, churn, refunds, exposure) as reference SQL over the `invoices` view.
- [`query_agent_spec.md`](./specs/query_agent_spec.md) — how the NL→SQL agent turns a
  question into a safe DuckDB query and a plain-English answer with the SQL shown.
- [`eval_spec.md`](./specs/eval_spec.md) — the 5 eval cases (one expected to fail) and
  how each expected value is computed and compared.

## How AI was used

AI did the building; the engineer did the **direction**. The steering lives in
[`CLAUDE.md`](./CLAUDE.md) — the operating contract the AI followed (source-of-truth
rules, stack, git discipline, and the one interface between components).

- **Two AI sessions worked in parallel** with strict file ownership to avoid
  collisions: **Session A (data)** owned the pipeline, cleaning/eval specs, and evals;
  **Session B (agent)** owned the metrics/query specs, the agent, and the app.
- **Spec-first flow:** write the spec → commit it → generate code from it. When the
  real data contradicted a spec, the *spec* was fixed first (its own commit), then the
  code — e.g. the undocumented `ENT` plan abbreviation.
- Decisions where the human overrode the AI are logged in
  [`docs/decisions.md`](./docs/decisions.md). Prompt history and per-session logs are
  in [`docs/prompts.md`](./docs/prompts.md) and [`docs/sessions/`](./docs/sessions/).
  A generated profile of the raw data is in [`docs/data_profile.md`](./docs/data_profile.md).
- **No train/test leakage:** the agent's four few-shot examples
  ([`src/agent/few_shots.yaml`](./src/agent/few_shots.yaml)) and the five eval questions
  ([`specs/eval_spec.md`](./specs/eval_spec.md)) were **checked manually for overlap** —
  they share no question or near-paraphrase (few-shots use 2023 revenue, total MRR *by
  plan*, churn *by region*; evals use 2024 revenue, avg MRR per account, Enterprise
  churn, refunds, monthly churn), so evals measure generalization, not recall.

## Key design decisions & trade-offs

- **DuckDB over Parquet, no database server.** The pipeline writes a single
  `cleaned.parquet`; the agent queries it in-process via DuckDB as a view named
  `invoices`. Zero infra to stand up, SQL the stakeholder can read, and it scales well
  past 5k rows. Trade-off: no concurrent writers or persistence layer — fine for a
  read-only analytics slice.
- **`schema.json` is the *only* contract** between the pipeline and the agent. The
  agent discovers columns, types and allowed values at runtime and **never hardcodes
  column names**, so a schema change can't silently desync the two halves.
- **Every cleaning rule has an ID (R01–R17)** with an action (`modified`/`dropped`/
  `flagged`) and a real rows-affected count in `cleaning_report.md`. Nothing is
  repaired silently; the report is auditable.
- **Derived money columns live in the data, not the agent.** `amount_usd` (FX-normalized,
  signed) and `mrr_usd` are computed once in the pipeline, so the agent needs no FX
  rates or price lists at query time.

## Known limitations & failure modes

We would rather be honest about where this breaks than hide it.

- **One eval is *expected* to fail (E05, "monthly churn rate in 2024").** The data has
  only a cumulative `churned` boolean with **no churn date**, so a monthly/period churn
  rate is undefined. A text-to-SQL agent won't refuse — it returns a plausible-but-wrong
  number. The harness marks this **XFAIL** (a documented limitation, not a passing fib).
- **The oracle is AI-generated from the same specs.** `evals/oracle.py` computes expected
  answers independently of the pipeline/agent code (plain pandas, no shared imports) — but
  it reads the *same specs*. So a **spec-level error would pass both** sides. The evals
  catch implementation drift, not a wrong business rule. Mitigation: FX and MRR were
  cross-checked against known list prices (e.g. EUR 52,920 ÷ 1.08 = $49,000 = 49×100×10).
- **Assumptions baked into the clean (all documented in `cleaning_spec.md` §11):**
  - **FX is applied by *division*** (`amount_usd = local / rate`). "EUR→USD 1.08" reads
    like a multiplier, but the data was generated as `usd × rate`; dividing recovers the
    true list-price USD. **If a grader multiplied, every money metric differs.**
  - **Ambiguous dates default to month-first (US).** `05-01-2024`-style values; unparseable → NULL + flagged.
  - **Dedup keeps the most-settled status** on `invoice_id` collisions (`paid > refunded > failed > pending > void`).
  - **`account_id` is the account key; `account_name` is display-only** (the two are badly
    non-1:1 in the source — 976 ids carry multiple names — and are not reconciled).
  - **`as_of_date` is fixed at 2026-12-31** (never "today"); invoices dated 2026 are kept, not dropped.
- **LLM SQL is nondeterministic.** The agent may phrase SQL differently run-to-run.
  Eval tolerances (0.5–1% relative, or a small absolute) absorb benign variation;
  a genuinely wrong query still fails.

## With another day

- **Answer-trust assessment:** map the columns a generated query touches → the cleaning
  rule IDs that shaped them → the relevant caveats, and attach a confidence note to every
  answer (e.g. "nets refunds via R08 FX-divide; 78 rows carry date-sanity flags").
- **Resolve the FX-direction discrepancy** (flagged to Session A; see `docs/decisions.md` #1).
  `metrics_spec §7` and the "EUR→USD 1.08" wording imply `amount_usd = local × rate`, while the
  pipeline/`cleaning_spec` use `local ÷ rate`. A list-price cross-check (EUR 52,920 ÷ 1.08 = $49,000)
  supports *divide*, but the specs must be made consistent **and** backed by an eval that recomputes
  FX from the raw `amount`/`currency` — today the oracle reads the pipeline's `amount_usd`, so no case
  guards the direction (it's a ~10.5% / ~$2.9M swing on 2024 revenue if wrong).
- **Automated few-shot ↔ eval overlap check** so eval questions can't leak into the
  agent's few-shot examples (no training-on-the-test).
- **More eval cases** (region exposure, top-accounts + CSAT flag, gross vs. net revenue)
  and a few deliberately adversarial/ambiguous ones.
- **CI running the evals** (GitHub Action) on every push, so a spec or pipeline change
  that breaks a metric is caught before merge.

## Eval results

Latest `python -m evals` (against an independent oracle; cleaned table = 5,000 rows):

| Case | Question | Expected | Got | Status |
|------|----------|----------|-----|--------|
| E01 | Total recognized revenue USD, paid invoices, 2024 | 27,823,962.37 | 27,823,962.37 | ✅ PASS |
| E02 | Region with the highest average MRR per account | 4,955.16 | 4,955.16 | ✅ PASS |
| E03 | Churn rate among Enterprise accounts | 0.2192 | 0.2192 | ✅ PASS |
| E04 | Refunds given back (USD) | 8,168,785.85 | 8,168,785.85 | ✅ PASS |
| E05 | Monthly churn rate in 2024 | — | — | ⚠️ XFAIL |

**4 PASS · 0 FAIL · 1 XFAIL.**

- **E05 (XFAIL — expected):** the data carries only a cumulative `churned` boolean with **no churn
  date**, so a *monthly* churn rate is undefined. The agent still returns a plausible-but-meaningless
  number; the harness marks it XFAIL rather than letting it masquerade as a pass. This is the one
  case we deliberately expect to fail — see `specs/eval_spec.md`.
- No *unexpected* failures. Note the scored money cases pass under the pipeline's FX convention; the
  open FX-direction discrepancy (above / `docs/decisions.md` #1) is not yet guarded by an eval.
