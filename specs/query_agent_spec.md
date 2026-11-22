# Query Agent Spec — CloudNova (Track B)

> Natural-language → SQL query agent over the cleaned invoice table. Turns a
> stakeholder question into a DuckDB query, runs it, and returns a plain-English
> answer **with the SQL shown**.
>
> This spec drives the code in `src/agent/` and `app/`. It depends **only** on
> the runtime contract in `CLAUDE.md` (`schema.json` + `specs/metrics_spec.md`),
> **not** on `specs/cleaning_spec.md`. The agent never imports or reads cleaning
> code; it discovers the schema from `schema.json` at runtime.

---

## 1. Interface

### Python API

```python
ask(question: str) -> {"answer": str, "sql": str, "rows": list}
```

- `answer` — one short paragraph in plain English that quotes the numbers (§6).
- `sql` — the exact DuckDB SQL that was executed (the last successful attempt).
- `rows` — the query result as a list of dicts (JSON-serializable), capped at
  the configured row limit (§4). Empty list is valid (question answered, no rows).
- On a handled failure (bad SQL after retry, unanswerable, guardrail rejection,
  config/data error) the function **still returns the dict**: `answer` explains
  the problem, `sql` holds the offending/last query (or `""` if none was built),
  `rows` is `[]`. The agent does not raise for these expected conditions.

### CLI

```
python -m app ask "<question>"
```

Prints, to stdout, in this order:
1. the **answer** paragraph,
2. a blank line, then the **SQL** under a clear label (e.g. `SQL:`).

`rows` are not dumped by default (keeps the terminal readable); the API exposes
them for programmatic use and `demo` may print a small preview. Exit code `0` on
a successful answer, non-zero on a hard error (missing API key / missing data).

---

## 2. Prompt assembly (at runtime, nothing hardcoded)

The NL→SQL system prompt is built fresh each call from three runtime inputs:

1. **`schema.json`** — the table name (`invoices`), `row_count`, and every column
   with its `type`, `nullable`, `description`, and `allowed_values`. The prompt
   renders these into a compact column list so the model knows exactly what
   exists. Column names are **never** hardcoded in agent code or in this spec —
   if the schema changes, the prompt changes automatically.
2. **`specs/metrics_spec.md`** — included so metric questions (revenue, MRR,
   churn, refunds, exposure, top-accounts) are answered with the *defined*
   formulas, not improvised ones (§3).
3. **Few-shot examples** — loaded from `agent.few_shots_path` (see `config.yaml`,
   `agent:` section). Each example is a `question → SQL` pair demonstrating the
   metrics_spec patterns in DuckDB dialect. Examples reference columns by the
   names present in `schema.json`; if a referenced column is absent from the
   loaded schema, that example is skipped rather than misleading the model.

   **No eval leakage (hard rule):** the few-shot set and the evaluation set
   (`evals/` / `specs/eval_spec.md`, owned by Session A) **must be disjoint**.
   The eval cases are seeded from the stakeholder questions in
   `docs/BUSINESS_CONTEXT.md`, so few-shots must **not** reuse those questions or
   their near-paraphrases, and must not hardcode an expected numeric answer.
   Few-shots teach the *metric shape* (status filters, time windows, per-account
   dedup, refund netting, USD columns) using **different** questions than any
   evaluated one — e.g. demonstrate the revenue pattern on a *different* year or
   region than the eval asks about. A metric pattern is taught at most once; the
   eval then tests that the agent generalizes it to the held-out question.
   Rationale: evals must measure generalization, not few-shot recall. The
   few_shots file should carry a header comment stating this constraint.

The prompt also states the dialect (DuckDB), the single view name, and the
guardrails (§4) as hard rules. No business constants (FX, list prices) appear in
the prompt — those are baked into the cleaned columns per metrics_spec §0/§7.

---

## 3. NL → SQL generation

- Target: **DuckDB SQL** over a single view **`invoices`** backed by
  `cleaned.parquet` (path from `config.yaml → paths.clean_dir`). The agent
  registers the parquet as the view `invoices` at startup.
- **Metric questions must follow `specs/metrics_spec.md`** — same status filters,
  time windows (by `invoice_date`), per-account dedup (latest invoice), refund
  netting, and USD columns. The few-shots encode these so the model reproduces
  them. If a question maps to a defined metric, the generated SQL should match
  that metric's shape.
- The model returns **one** SQL statement and nothing else; the agent strips any
  markdown fences / prose before execution.
- Non-metric but answerable lookups (counts, filters, group-bys over existing
  columns) are allowed as long as they respect the guardrails.

---

## 4. Guardrails & execution

- **Statement allow-list:** the SQL must be a **single** read-only statement
  beginning with `SELECT` or `WITH` (a CTE that resolves to a SELECT). Anything
  else — `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`,
  `COPY`, `PRAGMA`, `INSTALL`, multiple statements separated by `;`, etc. — is
  **rejected before execution** with a clear message; no retry on a rejection.
- **Row limit:** results are capped at `agent.max_rows` (config). If the model's
  SQL omits a `LIMIT` and the result would exceed the cap, the agent applies the
  cap (wrap or append `LIMIT`) and notes in the answer that results were
  truncated. Aggregates returning few rows are unaffected.
- **Timeout:** each query runs under `agent.query_timeout_s` (config). A timeout
  is treated as a handled failure (clear message, no infinite work).
- **Retry-once on SQL error:** if execution raises (parse/binding/runtime error),
  the agent makes **one** follow-up LLM call that includes the failed SQL **and**
  the exact DuckDB error text, asking for a corrected single statement. The
  corrected SQL is re-validated against the allow-list and re-run **once**. If it
  still fails, the agent returns a clear failure (the error, the last SQL) and
  does **not** loop further.
- All config values (`model`, `max_rows`, `query_timeout_s`, `few_shots_path`)
  come from `config.yaml → agent`; none are hardcoded.

---

## 5. Unanswerable / ambiguous questions

- If the question cannot be answered from the available columns (needed data
  isn't in `schema.json`), or is too ambiguous to map to a single query, the
  agent says so plainly and explains what's missing or unclear. It returns
  `rows: []` and an `answer` that states the limitation.
- The agent **never invents a number** or fabricates rows. An answer paragraph
  must only quote values that appear in the actual query `rows`. If there are no
  rows, the answer does not assert a figure.
- Where a question is answerable but rests on a `metrics_spec` assumption (e.g.
  churn is a cumulative snapshot, MRR from latest invoice), the answer may note
  that assumption briefly so the stakeholder isn't misled.

---

## 6. Answer step

- After a successful query, a **second, short LLM call** converts the `rows`
  (plus the original question) into **one plain-English paragraph** that quotes
  the actual numbers from the result (e.g. the dollar figure, the region, the
  rate). It must not introduce values not present in `rows`.
- The paragraph is concise (a few sentences), names units/currency (USD), and
  rounds money sensibly for readability while the raw values stay in `rows`.
- This call is intentionally cheap; if it fails, the agent falls back to a
  deterministic rendering of `rows` rather than erroring out, so the user still
  gets `sql` + data.

---

## 7. Error handling (one clear message, no stack traces)

Per `CLAUDE.md`, every error surfaces as a single clear line, never a raw
traceback:

- **Missing API key** (`ANTHROPIC_API_KEY` absent from `.env`/env): one message
  telling the user to set it; non-zero exit on the CLI. No LLM call attempted.
- **Missing / unreadable data** (`cleaned.parquet` or `schema.json` not found):
  one message telling the user to run `python -m app clean` first; non-zero exit.
- **Bad SQL after the single retry:** handled failure dict (§4) — clear message +
  last SQL, no traceback.
- **Guardrail rejection:** clear message naming that only read-only SELECT/WITH
  queries are allowed.
- **Timeout / LLM/network error:** one clear message; the CLI exits non-zero.

Internally exceptions may carry detail for logging, but what reaches the user is
always the single-line summary.

---

## 8. Out of scope (keep it simple)

No conversation memory / multi-turn state, no caching, no vector store or RAG, no
charts, no auth. One question in → one answer + SQL out. These are noted as
possible "next steps" for the README, not built here.
```