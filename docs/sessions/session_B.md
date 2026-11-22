# Session B (agent) — trimmed transcript

> Session B owns `specs/metrics_spec.md`, `specs/query_agent_spec.md`, `src/agent/`,
> `app/`, `tests/`, and the `agent:` block of `config.yaml`. Trimmed to the steering
> prompts and the actions taken (same style as `session_A.md`).

---

❯ Read CLAUDE.md + BUSINESS_CONTEXT + TASK. Write `specs/metrics_spec.md`. No code.
  Exact definitions of revenue, MRR, churn (+ others the stakeholder Qs need):
  formulas as SQL-like pseudocode over `invoices`, edge cases, ambiguities marked
  `ASSUMPTION:`. Commit + push (this file only).

● Wrote `specs/metrics_spec.md`: recognized revenue (paid+refunded net, by
  `invoice_date`), MRR (`list_price*seats*(1-disc/100)`, point-in-time from each
  account's latest invoice), churn (account-level cumulative), refunds, exposure,
  top-accounts + CSAT. Key assumptions: A1 `amount_usd` is as-billed; A2 pipeline
  derives `amount_usd`/`mrr_usd` so the agent needs no constants; A4/A5 latest-invoice
  dedup, churned ⇒ $0 MRR; A7 churn is a cumulative snapshot.
  → commit `spec: metrics definitions`.

❯ Write `specs/query_agent_spec.md`. No code. Depend only on the schema.json contract,
  not cleaning_spec. (interface, runtime prompt assembly, DuckDB, guardrails, retry,
  unanswerable, answer step, errors.) Commit + push.

● Wrote the agent spec: `ask()->{answer,sql,rows}`; prompt built at runtime from
  schema.json + metrics_spec + few-shots (no hardcoded columns); SELECT/WITH-only
  guardrail; row cap + timeout from config; retry-once on SQL error; never invent a
  number; second LLM call renders the paragraph. → commit `spec: query agent`.

❯ The few-shot examples need to be different from the eval samples to prevent leaking.

● Added a hard no-leakage rule to the spec: few-shots must be disjoint from
  `evals/`/`eval_spec.md`; teach the metric *shape* on different questions, no expected
  numbers. → commit `spec: require few-shot set disjoint from eval set`.
  (Rebased onto Session A's concurrent work; staged only my own file.)

❯ Implement the agent in `src/agent/` + `app/`. Build a 10-row fixture
  (`tests/fixtures/`, path overridable via `CLEAN_DIR`). 4 generic few-shots (don't
  open eval_spec). CLI clean/ask/demo. `tests/test_guardrails.py` (no API). Run tests,
  then one real `ask`. Commit after each working step.

● Built `src/agent/` (config, schema, sql_guard, db, prompts, llm, agent, errors),
  `src/agent/few_shots.yaml` (4 examples, each with a `requires:` column list + a
  no-leakage header), `app/__main__.py`, fixture parquet+schema.json, and
  `tests/test_guardrails.py` + `conftest.py`. **17 tests pass**; a real `ask` on the
  fixture returned correct SQL + a numeric answer. Full `demo` answered all three
  sample questions. → commit `agent: NL->SQL query agent, CLI, guardrails, fixture + tests`.

❯ (diagnostic) `git pull --rebase`; run `clean`, `demo`, `evals`; for each unexpected
  FAIL classify A pipeline / B agent / C oracle / D spec; show evidence; change nothing.

● clean: 5125→5000 rows. demo: all three answered. evals: **4 PASS / 0 FAIL / 1 XFAIL**
  (E05 is the designed expected-fail). No unexpected FAILs. Surfaced one latent item:
  FX direction — pipeline/config/cleaning_spec **divide** by rate, while
  BUSINESS_CONTEXT wording + `metrics_spec §7` imply **multiply** (~$2.9M / 10.5% on
  2024 revenue). Evals don't catch it (`oracle.py` reads the pipeline's `amount_usd`).
  Evidence (EUR 52,920 ÷ 1.08 = $49,000 list-price-consistent) actually favors divide.

❯ Keep the flag to Session A (I'll check later). Write it up as a discrepancy and
  document it; add it as an improvement in the README.

● Changed no FX logic. Flagged the discrepancy in `metrics_spec §7`, logged it in
  `docs/decisions.md` (#1, owner = Session A), added a README "With another day" item +
  filled the README "Eval results" table. → commit `docs: flag FX-direction discrepancy`.

❯ Write `docs/architecture.md` (Mermaid flowchart matching the code) and embed the same
  diagram in the README. Verify the README run commands. Commit + push. Then session
  log, PR dev→main, and a manual few-shot/eval overlap check noted in the README.

● Wrote `docs/architecture.md` + embedded the diagram under README "## Architecture".
  Verified `pip install`, `python -m app ask`, `python -m app demo`, `python -m evals`
  run as documented. Manually confirmed few_shots.yaml vs eval_spec.md share no
  question/paraphrase; noted it in the README. → commit `docs: architecture diagram`.
