# Eval Spec — CloudNova (Track B, Session A)

> Five cases drawn from the stakeholder questions in `docs/BUSINESS_CONTEXT.md`,
> weighted to revenue / MRR / churn. Expected values are computed **independently**
> by `evals/oracle.py` (plain pandas over `data/clean/cleaned.parquet`, no pipeline
> or agent code) and frozen into `evals/cases.yaml`. The harness (`python -m evals`)
> asks the agent each question and compares the first numeric value in
> `result["rows"]` against the expected value within tolerance.
>
> Exactly **one** case (E05) is expected to fail — see §E05.

All money is USD. Metric definitions follow `specs/metrics_spec.md`; the oracle
re-implements them from scratch, it does not import them.

---

## E01 — Recognized revenue, 2024 (BUSINESS_CONTEXT Q1) · revenue

- **Question:** "What was our total recognized revenue in USD for paid invoices in 2024?"
- **Computation:** `SUM(amount_usd)` over rows where `status IN ('paid','refunded')`
  and `invoice_date` in `[2024-01-01, 2025-01-01)`. Refunds (negative `amount_usd`)
  net against revenue; `pending`/`failed`/`void` excluded.
- **Expected shape:** single scalar (USD).
- **Tolerance:** relative **0.5%** (absorbs inclusive-vs-exclusive date-edge and
  whether the agent nets refunds, but not a wrong FX direction or wrong status set).

## E02 — Region with highest average MRR per account (Q2) · MRR

- **Question:** "Which region has the highest average MRR per account?"
- **Computation:** reduce to one row per `account_id` = its **latest** invoice
  (`invoice_date DESC`, tie-break `invoice_id DESC`); a churned account contributes
  `mrr_usd = 0`. Average that per-account current MRR by `region`; take the **max**
  region. Compared value = that region's average MRR (scalar); the region label is
  reported but not range-checked.
- **Expected shape:** scalar (USD) = the winning region's avg MRR per account.
- **Tolerance:** relative **1%** (point-in-time dedup is the hard part; small ties
  in "latest invoice" shouldn't flip the number much).

## E03 — Enterprise churn rate (Q4) · churn

- **Question:** "What is the churn rate among Enterprise accounts?"
- **Computation:** one row per `account_id` (latest invoice, as E02); keep
  `plan = 'Enterprise'`; `churn_rate = mean(churned)` as a fraction 0–1.
- **Expected shape:** scalar fraction in [0,1].
- **Tolerance:** absolute **0.01** (1 percentage point).

## E04 — Total refunds given back (Q3) · revenue

- **Question:** "How much have we given back in refunds?"
- **Computation:** `-SUM(amount_usd)` over `status = 'refunded'`, reported as a
  positive magnitude.
- **Expected shape:** scalar (USD, positive).
- **Tolerance:** absolute **$0.01** (pure sum over one status; should be exact).

## E05 — Monthly churn rate in 2024 · churn · **EXPECTED FAIL (XFAIL)**

- **Question:** "What was our monthly churn rate in 2024?"
- **Why it must fail:** the data cannot support this definition. `churned` is a
  single **cumulative, point-in-time** boolean per account (metrics_spec A7) with
  **no churn date** — there is no way to attribute a churn event to a month or to
  2024. A proper monthly/period churn rate (churned-in-period ÷ active-at-start) is
  therefore **undefined** from this dataset.
- **Expected shape:** `expected: null` — no defensible numeric answer exists.
- **Behaviour under test:** a text-to-SQL agent will not refuse; it will return a
  *plausible-looking* number (e.g. overall cumulative account-churn fraction, or a
  per-invoice fraction), answering a different question than the one asked. The
  harness records the agent's output and marks the case **XFAIL** — a pass of the
  build, a documented failure of pure NL→SQL. Fixing it would require a churn-event
  timestamp the ledger does not contain.

---

## Harness contract

- `cases.yaml` holds, per case: `id`, `question`, `expected` (number or null),
  `tolerance` (`{type: relative|absolute, value: n}`), `xfail` (bool), `metric`.
- Compare: extract the **first numeric value** from `result["rows"]`; PASS if within
  tolerance; FAIL otherwise. `xfail` cases are reported XFAIL regardless and never
  fail the build. Unexpected FAIL on a non-xfail case → non-zero exit.
- Missing agent (`src.agent`) or missing `cleaned.parquet` → clear message, clean exit.
