# Cleaning Spec — CloudNova (Track B, Session A)

> The authoritative description of how `data/raw/cloudnova_invoices.csv` becomes
> the clean DuckDB view `invoices`. Code in `src/pipeline/` is generated from
> THIS document. Evidence for every rule is in `docs/data_profile.md`.
> Reconciled with `specs/metrics_spec.md` (Session B): the pipeline must emit
> `amount_usd` and `mrr_usd` so the agent needs no business constants at query time.

Constants (FX, list price, as-of date) live in `config.yaml → pipeline`, never in code.

---

## 1. Target schema (view `invoices`, one row per invoice)

| # | column | type | nullable | constraints / allowed values |
|---|--------|------|----------|-------------------------------|
| 1 | `invoice_id` | VARCHAR | no | `INV-\d+`; **unique after dedup** |
| 2 | `account_id` | VARCHAR | no | `ACC-\d+`; account key (per metrics_spec) |
| 3 | `account_name` | VARCHAR | yes | display only; not an account key (see §4) |
| 4 | `contact_email` | VARCHAR | yes | valid email after `_at_`→`@`; else NULL+flag |
| 5 | `region` | VARCHAR | yes | one of NA / EMEA / APAC / LATAM, else NULL |
| 6 | `industry` | VARCHAR | yes | free text; NULL if missing |
| 7 | `plan` | VARCHAR | no | **Starter / Pro / Enterprise** |
| 8 | `billing_cycle` | VARCHAR | no | **monthly / annual** |
| 9 | `seats` | BIGINT | no | integer ≥ 1 |
| 10 | `currency` | VARCHAR | no | USD / EUR / GBP |
| 11 | `amount_usd` | DOUBLE | yes | as-billed, FX→USD, **signed** (refunds < 0); NULL if unparseable+flag |
| 12 | `discount_pct` | DOUBLE | no | 0–100 |
| 13 | `status` | VARCHAR | no | **paid / pending / failed / refunded / void** |
| 14 | `payment_method` | VARCHAR | yes | credit_card / ACH / wire / invoice; NULL if blank |
| 15 | `signup_date` | DATE | yes | parsed; NULL+flag if unparseable |
| 16 | `invoice_date` | DATE | yes | parsed; NULL+flag if unparseable (excluded from time windows) |
| 17 | `churned` | BOOLEAN | no | true / false |
| 18 | `csat_score` | DOUBLE | yes | 1–5; NULL if missing |
| 19 | `support_tickets` | BIGINT | no | integer ≥ 0 |
| 20 | `mrr_usd` | DOUBLE | no | derived monthly recurring revenue, USD (§ R09) |

Columns 11 (`amount_usd`) and 20 (`mrr_usd`) are **added**; raw `amount` is
replaced by `amount_usd`.

---

## 2. Disguised nulls

Before any rule, trim whitespace and treat these (case-insensitive) as missing →
NULL: `""`, `n/a`, `na`, `null`, `none`, `nan`, `-`, `--`, `?`, `unknown`.
Applies to all VARCHAR columns. (Profile: region 25.1%, payment_method 12.4%,
csat 12.2%, industry 8.2%, email 5.7% missing.)

---

## 3. Dedup

- **Key:** `invoice_id`. Profile: 5125 rows, 5000 distinct ids; 163 exact-duplicate
  rows; 124 ids repeat; of those only ~43 differ, and only on `status`.
- **R13 — exact duplicates:** after normalization (R01–R12), drop rows identical
  on all columns, keeping the first. `action: dropped`.
- **R14 — surviving `invoice_id` collisions:** if an id still has >1 row, keep ONE
  by status priority `paid > refunded > failed > pending > void`; tie-break by
  larger `|amount_usd|`, then first occurrence. Drop the rest. `action: dropped`.
  `ASSUMPTION A-DEDUP:` conflicting near-dupes are the same economic invoice
  re-reported by different source systems; the most-settled status is the truth.

---

## 4. Category / status / account normalization

Trim + collapse internal whitespace, lowercase for matching. **R01** covers the
trim/whitespace fix (1023 plan values alone carried stray spaces).

**R02 — plan** (match on lowercased, stripped; keyword rules):
| canonical | matches |
|-----------|---------|
| Starter | `starter`, `start`, `tier 1` |
| Pro | `pro`, `professional`, `tier 2` |
| Enterprise | `enterprise`, `tier 3` |

**R03 — status:**
| canonical | matches |
|-----------|---------|
| paid | paid, complete, completed, success |
| pending | pending, in_review, awaiting |
| failed | failed, declined, error |
| refunded | refunded, refund, charged_back |
| void | void, cancelled, canceled |

**R04 — billing_cycle:** `monthly`←{monthly}; `annual`←{annual, annually, yearly}.

**R05 — payment_method:** `credit_card`←{credit_card, credit card}; `ACH`←{ach};
`wire`←{wire, wire transfer}; `invoice`←{invoice}; blank→NULL.

**R06 — churned → BOOLEAN:** true←{true, yes, 1, y}; false←{false, no, 0, n}.

**Account resolution (R-ACCT, flag only):** `account_id` and `account_name` are
**not** 1:1 — 976 ids carry >1 name and 200 names span many ids (profile §4).
Per `metrics_spec`, `account_id` is the authoritative account key; `account_name`
is kept as a descriptive label only and is **not** reconciled. `ASSUMPTION
A-ACCT:` do not merge/split accounts on name; report the inconsistency count in
`cleaning_report.md`.

Any value not matched by R02–R06 → NULL + flag (should be ~0).

---

## 5. Date parsing (R10)

Accepted formats, tried in **priority order** (first match wins):
1. `YYYY-MM-DD` (ISO) — unambiguous.
2. `YYYY/MM/DD` — unambiguous (year first).
3. `Mon D YYYY` (e.g. `Jan 5 2024`) — unambiguous.
4. Numeric with `/` or `-` separators, `A?B?YYYY` — **ambiguous** day/month:
   - if first component > 12 → **day-first** (`DD/MM/YYYY`);
   - else if second component > 12 → **month-first** (`MM/DD/YYYY`);
   - else default **month-first (US)**.

`ASSUMPTION A-DATE:` default month-first for genuinely ambiguous values
(BUSINESS_CONTEXT flags `05-01-2024` as ambiguous; US month-first is the most
common convention in this export and matches the slash examples). Ambiguous rows
resolved this way are counted in the report.

Unparseable → NULL + flag (**R17** for null `invoice_date`: kept but excluded
from every time window, per metrics_spec §8).

**R16 — date sanity:** `invoice_date` after `as_of_date` (2026-12-31) or before
2015, or `invoice_date < signup_date` → flag (kept, not dropped). Profile: ~609
invoices dated 2026 — plausible, retained; the "in 2024" filter excludes them.

---

## 6. FX → USD (R08) — the headline landmine

Parse `amount` (R07): strip `$ € £`, thousands commas, and trailing currency
words/codes (`USD`/`EUR`/`GBP`); keep the sign (refunds negative); `"31432"` →
`31432.0`. 1683 amounts need this; 272 are negative refunds.

Convert to USD using `config.yaml → fx_rates_to_usd`:

```
amount_usd = amount_local / fx_rates_to_usd[currency]      -- DIVIDE, sign preserved
```

`ASSUMPTION A-FX:` **divide**, not multiply. The arrow notation "EUR→USD 1.08"
reads like a multiplier, but the data was generated as
`local = usd_base × rate`, so USD is recovered by dividing. Verified: EUR 52920 ÷
1.08 = 49000, GBP 31432 ÷ 1.27 = 24750 — exact `list_price × seats × 10`. Multiplying
yields 57153 / 39918, which match no real price. Finance's "true USD" is the
divide result. Rate applied is keyed by the row's `currency` (USD → 1.0).

If `amount` is unparseable → `amount_usd = NULL` + flag (excluded from money sums).

---

## 7. MRR derivation (R09)

Per `metrics_spec` §2, independent of currency and billing_cycle:

```
mrr_usd = list_price_usd[plan] × seats × (1 − discount_pct / 100.0)
```

`list_price_usd` from config (`Starter 49, Pro 99, Enterprise 299`). Computed
after plan (R02), seats (R12) and discount are clean. Not nullable (plan/seats
are non-null). The 10-month annual factor is **not** applied here — MRR is
monthly; it only affects what is *billed* (already captured in `amount_usd`).

---

## 8. Numeric casts (R12)

`seats`, `support_tickets` → BIGINT; `csat_score`, `discount_pct` → DOUBLE
(`csat` NULL if blank). Profile: all seats ≥ 1, discount ∈ {0,10,15,20,25}
(in range), csat ∈ 1–5 — no out-of-range values to drop.

**R11 — emails:** replace `_at_`→`@` (142 rows); if still not matching
`^[^@\s]+@[^@\s]+\.[^@\s]+$` → NULL + flag. `action: modified|flagged`.

---

## 9. Drop vs flag summary

Rules are applied in the order listed (dependency-correct: numeric casts R12
precede the money derivations R08/R09 that consume them; dedup R13/R14 and flags
R16/R17 run last, over fully-normalized rows).

| order | ID | description | action |
|-------|----|-------------|--------|
| 1 | R01 | trim / collapse whitespace, strip disguised nulls → NULL | modified |
| 2 | R02 | normalize `plan` → Starter/Pro/Enterprise | modified |
| 3 | R03 | normalize `status` → canonical 5 | modified |
| 4 | R04 | normalize `billing_cycle` → monthly/annual | modified |
| 5 | R05 | normalize `payment_method`; blank → NULL | modified |
| 6 | R06 | `churned` → BOOLEAN | modified |
| 7 | R12 | cast numerics (seats, support_tickets, csat, discount) | modified |
| 8 | R07 | parse `amount` string → signed numeric (local) | modified |
| 9 | R08 | FX convert local → `amount_usd` (**divide** by rate) | modified |
| 10 | R09 | derive `mrr_usd` = list×seats×(1−disc/100) | added |
| 11 | R10 | parse `signup_date` / `invoice_date`; ambiguous = month-first | modified |
| 12 | R11 | fix `_at_`→`@`; invalid email → NULL | modified / flagged |
| 13 | R13 | drop exact-duplicate rows | dropped |
| 14 | R14 | resolve `invoice_id` collisions (status priority) | dropped |
| 15 | R16 | date sanity flag (future / pre-2015 / invoice<signup) | flagged |
| 16 | R17 | flag null `invoice_date` (excluded from time windows) | flagged |

Only R13/R14 remove rows. Everything else repairs or flags — no silent data loss.

---

## 10. Outputs (contract — see CLAUDE.md)

Written to `data/clean/`:
- **`cleaned.parquet`** — the table above, queried by DuckDB as view `invoices`.
- **`schema.json`** — `{table, row_count, columns[{name,type,nullable,description,
  allowed_values,rules_applied}], rules[{id,description,action,rows_affected}]}`.
- **`cleaning_report.md`** — rows in/out, and rows affected per rule R01–R17.

---

## 11. Open questions — resolved (assumptions index)

- **A-FX:** FX is applied by **division** (generation-consistent, finance-meaningful).
- **A-DATE:** ambiguous numeric dates parsed **month-first (US)**; unparseable → NULL+flag.
- **A-DEDUP:** `invoice_id` collisions resolved by status priority `paid>refunded>failed>pending>void`.
- **A-ACCT:** `account_id` is the account key; `account_name` is display-only, not reconciled.
- **as_of_date** fixed at **2026-12-31** (reporting horizon / date upper bound), never "today".
- **Future invoice dates (2026)** are retained, not dropped; year filters exclude them naturally.
