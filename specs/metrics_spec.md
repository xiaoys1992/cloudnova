# Metrics Spec — CloudNova (Track B)

> Source of truth for every business metric the NL query agent must compute.
> Formulas are plain SQL-like pseudocode over the DuckDB view `invoices`
> (one row per invoice, produced by the cleaning pipeline — see Contracts in
> `CLAUDE.md`). The agent translates stakeholder questions into these patterns;
> it must **never** re-implement the business logic differently.

Scope: this spec defines *what the numbers mean*. It does not define cleaning or
SQL-generation; see `specs/cleaning_spec.md` (Session A) and
`specs/query_agent_spec.md` (Session B).

---

## 0. Columns this spec depends on (contract with the cleaning pipeline)

Metrics below assume the pipeline has already normalized/deduplicated and emits
these columns in `cleaned.parquet` / `schema.json`. Names are the canonical
snake_case the agent discovers at runtime from `schema.json` — they are listed
here only so the formulas are concrete.

| Column | Type | Notes used by metrics |
|--------|------|-----------------------|
| `invoice_id` | VARCHAR | One row per invoice after dedup. |
| `account_id` | VARCHAR | Customer account. |
| `region` | VARCHAR | NA / EMEA / APAC / LATAM. |
| `plan` | VARCHAR | Normalized to `Starter` / `Pro` / `Enterprise`. |
| `billing_cycle` | VARCHAR | `monthly` / `annual`. |
| `seats` | BIGINT | Licensed seats on the invoice. |
| `discount_pct` | DOUBLE | 0–100. |
| `status` | VARCHAR | Canonical: `paid` / `pending` / `failed` / `refunded` / `void`. |
| `amount_usd` | DOUBLE | **As-billed** invoice amount, FX-normalized to USD, **signed** (refunds negative). |
| `mrr_usd` | DOUBLE | Per-invoice derived MRR in USD (see §2). |
| `invoice_date` | DATE | When the invoice was issued. Drives time windows. |
| `churned` | BOOLEAN | Whether the account has since churned. |
| `csat_score` | DOUBLE | Latest CSAT 1–5, nullable. |

> **ASSUMPTION (A1):** `amount_usd` is the amount actually billed on the invoice
> (already net of `discount_pct` and FX-converted). Recognized revenue therefore
> **sums `amount_usd` directly** and does *not* recompute from list price ×
> seats. `discount_pct` is only re-applied when deriving `mrr_usd` (§2).
>
> **ASSUMPTION (A2):** The pipeline derives `amount_usd` and `mrr_usd` so the
> agent needs no business constants (FX rates, list prices) at query time. Those
> constants live in `config.yaml → pipeline` (owned by Session A), not in agent
> code. If the delivered schema lacks `amount_usd`/`mrr_usd`, see §7 fallback.

**Business constants (reference — authoritative copy lives in `config.yaml`):**
list price per seat/month USD `Starter=49, Pro=99, Enterprise=299`;
FX→USD `EUR=1.08, GBP=1.27`; annual invoices bill **10** months, not 12.

---

## 1. Recognized revenue

Only `paid` invoices are revenue. `refunded` rows carry a **negative**
`amount_usd` and **net against** revenue. `pending` / `failed` / `void` are
excluded entirely.

```sql
-- Total recognized revenue, USD, all time
SELECT SUM(amount_usd) AS recognized_revenue_usd
FROM invoices
WHERE status IN ('paid', 'refunded');
```

Time-windowed (stakeholder Q1 — "revenue in 2024"), filtered on `invoice_date`:

```sql
-- Recognized revenue for calendar year 2024
SELECT SUM(amount_usd) AS recognized_revenue_usd_2024
FROM invoices
WHERE status IN ('paid', 'refunded')
  AND invoice_date >= DATE '2024-01-01'
  AND invoice_date <  DATE '2025-01-01';
```

- **Time window:** by `invoice_date` (when revenue was invoiced), never
  `signup_date`. A year `YYYY` means `[YYYY-01-01, (YYYY+1)-01-01)`.
- **Edge — annual plans:** the annual lump sum lands on one invoice; it is
  counted once as billed. Do **not** spread it across months and do **not**
  convert it to MRR for revenue (MRR is a separate metric, §2).
- **Edge — refunds inside the window:** a refund is attributed to the period of
  its own `invoice_date`, so a 2024 refund of a 2023 charge reduces 2024 revenue.
  `ASSUMPTION (A3)`.
- **Edge — gross vs net revenue:** this metric is net of refunds. For gross
  (paid only) drop `'refunded'` from the `IN` list.

---

## 2. MRR (monthly recurring revenue)

Per-invoice MRR, in USD (derived as column `mrr_usd` by the pipeline):

```sql
-- Definition of mrr_usd (pipeline computes this; shown for reference)
mrr_usd = list_price_usd[plan] * seats * (1 - discount_pct / 100.0)
```

- Independent of `billing_cycle`, `currency`, and `amount_usd`: an annual
  invoice maps to the **same** underlying monthly figure (no annual lump sum,
  no 10-month factor here — that factor only affects what is *billed*, not MRR).
- MRR is a **point-in-time** quantity, so "current MRR" is taken from each
  account's **most recent** invoice, not summed across its invoice history.

### 2a. Current MRR per account

```sql
WITH ranked AS (
  SELECT *,
         ROW_NUMBER() OVER (
           PARTITION BY account_id
           ORDER BY invoice_date DESC, invoice_id DESC
         ) AS rn
  FROM invoices
),
account_current AS (          -- one latest row per account
  SELECT account_id, region, plan, churned, mrr_usd
  FROM ranked
  WHERE rn = 1
)
SELECT account_id,
       CASE WHEN churned THEN 0 ELSE mrr_usd END AS current_mrr_usd
FROM account_current;
```

> **ASSUMPTION (A4):** Point-in-time facts for an account (its current `plan`,
> `region`, `mrr_usd`, churn state) come from its **latest invoice** by
> `invoice_date`, tie-broken by `invoice_id DESC`.
>
> **ASSUMPTION (A5):** A **churned** account contributes **$0** current MRR
> (the subscription is no longer active). Its historical invoices still count
> toward historical revenue (§1).

### 2b. Average MRR per account by region (stakeholder Q2)

```sql
WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (
           PARTITION BY account_id
           ORDER BY invoice_date DESC, invoice_id DESC) AS rn
  FROM invoices
),
account_current AS (
  SELECT region,
         CASE WHEN churned THEN 0 ELSE mrr_usd END AS current_mrr_usd
  FROM ranked WHERE rn = 1
)
SELECT region,
       AVG(current_mrr_usd) AS avg_mrr_per_account_usd,
       COUNT(*)             AS accounts
FROM account_current
GROUP BY region
ORDER BY avg_mrr_per_account_usd DESC;
```

- "Per account" means the denominator is **distinct accounts**, not invoices.
- `ASSUMPTION (A6):` average is taken over **all** accounts in the region
  (churned included at $0), giving a blended book-of-business figure. To measure
  only live subscriptions, add `WHERE NOT churned` — reported as an alternate.

---

## 3. Refunds (stakeholder Q3)

```sql
-- How much we've given back, reported as a positive magnitude
SELECT -SUM(amount_usd) AS refunds_given_back_usd   -- amounts are negative
FROM invoices
WHERE status = 'refunded';
```

- Refund rows are the only negative `amount_usd`. Reported as a positive number
  for the stakeholder; internally they are negative and net into §1.

---

## 4. Churn rate (stakeholder Q4)

Churn is an **account-level** attribute (`churned`), not per-invoice, so dedup to
one row per account first (latest invoice, §2a) before counting.

```sql
WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (
           PARTITION BY account_id
           ORDER BY invoice_date DESC, invoice_id DESC) AS rn
  FROM invoices
),
account_current AS (
  SELECT account_id, plan, churned
  FROM ranked WHERE rn = 1
)
SELECT plan,
       COUNT(*)                                        AS accounts,
       SUM(CASE WHEN churned THEN 1 ELSE 0 END)        AS churned_accounts,
       AVG(CASE WHEN churned THEN 1.0 ELSE 0.0 END)    AS churn_rate
FROM account_current
GROUP BY plan
ORDER BY plan;
```

- `churn_rate` is a fraction 0–1 (× 100 for a percentage).
- Enterprise-vs-Starter is just reading the relevant rows of this result.
- `ASSUMPTION (A7):` churn is a cumulative snapshot ("has the account **ever**
  churned"), not a per-period rate — the data gives no churn date. The `plan`
  attributed is the account's latest-invoice plan.

---

## 5. Payment exposure — pending / failed (stakeholder Q6)

```sql
SELECT status,
       COUNT(*)        AS invoices,
       SUM(amount_usd) AS exposed_usd
FROM invoices
WHERE status IN ('pending', 'failed')
GROUP BY status;                 -- drop GROUP BY for a single combined total
```

- "Exposed $" = money invoiced but not recognized because payment hasn't
  cleared. Uses `amount_usd` (as billed). `void` is excluded — it is cancelled,
  not outstanding.

---

## 6. Top accounts by revenue + CSAT flag (stakeholder Q5)

```sql
SELECT account_id,
       MAX(account_name)                               AS account_name,
       SUM(amount_usd)                                 AS revenue_usd,
       MAX(csat_score)                                 AS csat_score,   -- "latest CSAT"
       (MAX(csat_score) IS NOT NULL
        AND MAX(csat_score) <= 2)                      AS low_csat_flag
FROM invoices
WHERE status IN ('paid', 'refunded')
GROUP BY account_id
ORDER BY revenue_usd DESC
LIMIT 5;
```

- Revenue per account uses the §1 recognized-revenue rule (net of refunds).
- `ASSUMPTION (A8):` `csat_score` is a per-account "latest" value repeated on
  the account's rows, so `MAX()` (= the single distinct value) represents it.
  A null CSAT is **not** flagged low (unknown ≠ bad).

---

## 7. Fallback if `amount_usd` / `mrr_usd` are absent

If the delivered `schema.json` lacks the derived columns, the agent computes
them inline from raw columns, applying the §0 constants from `config.yaml`:

```sql
amount_usd ≈ raw_amount_numeric * fx_to_usd[currency]      -- sign preserved
mrr_usd    ≈ list_price_usd[plan] * seats * (1 - discount_pct/100.0)
```

This is a degraded path (couples the agent to constants) and should trigger a
spec reconciliation with Session A rather than shipping silently.

---

## 8. Cross-cutting rules

- **One row per `invoice_id`:** dedup is the pipeline's job; metrics assume it is
  done. If duplicates remain, SUM-based metrics over-count — surface, don't mask.
- **Nulls:** excluded from the metric they'd corrupt (null CSAT not flagged;
  null `invoice_date` falls outside every time window and is excluded from
  windowed revenue — flag such rows in the cleaning report).
- **Currency:** every money metric is USD. Never sum raw `amount` across
  currencies without conversion.
- **Status is king:** revenue inclusion is decided **only** by canonical
  `status`, never by payment method or amount sign alone.
```