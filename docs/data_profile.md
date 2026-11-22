# CloudNova Raw Data Profile

Source: `data/raw/cloudnova_invoices.csv` — **5125 rows**, 19 columns. No cleaning applied; all values read as raw strings.

## 1. Expectation table (from BUSINESS_CONTEXT)

| column | meaning | expected type | expected values/format |
| --- | --- | --- | --- |
| invoice_id | Invoice key (unique-ish; dup in near-dupes) | VARCHAR | INV-xxxxxx |
| account_id | Customer account id | VARCHAR | ACC-xxxx |
| account_name | Customer account name | VARCHAR | free text, 1:1 with account_id |
| contact_email | Billing contact (nullable/malformed) | VARCHAR | valid email; some _at_ for @ |
| region | Region | VARCHAR | NA / EMEA / APAC / LATAM |
| industry | Account industry (nullable) | VARCHAR | free text |
| plan | Subscription plan (dirty) | VARCHAR | Starter / Pro / Enterprise |
| billing_cycle | Billing cycle (dirty) | VARCHAR | monthly / annual |
| seats | Licensed seats | BIGINT | positive integer |
| currency | Invoice currency | VARCHAR | USD / EUR / GBP |
| amount | Invoice amount (messy string) | DOUBLE | numeric; negative if refunded |
| discount_pct | Discount percentage | DOUBLE | 0-100 |
| status | Payment status (dirty) | VARCHAR | paid/pending/failed/refunded/void |
| payment_method | Payment method (dirty/nullable) | VARCHAR | credit_card/ACH/wire/invoice |
| signup_date | Account signup date (dirty) | DATE | mixed date formats |
| invoice_date | Invoice issue date (dirty) | DATE | mixed date formats |
| churned | Account churned (dirty bool) | BOOLEAN | true/TRUE/Yes/1/Y vs false/... |
| csat_score | Latest CSAT (nullable) | BIGINT | 1-5 |
| support_tickets | Tickets opened | BIGINT | non-negative integer |

## 2. Per-column profile


### `invoice_id`
- expected: VARCHAR — INV-xxxxxx
- missing (incl. disguised): **0** (0.0%) | distinct present: **5000**
- top values: 'INV-104263'×3, 'INV-104706'×2, 'INV-100093'×2, 'INV-101367'×2, 'INV-100071'×2, 'INV-102011'×2, 'INV-102377'×2, 'INV-104401'×2, 'INV-103521'×2, 'INV-104040'×2, 'INV-100630'×2, 'INV-104009'×2, 'INV-101244'×2, 'INV-102422'×2, 'INV-103377'×2

### `account_id`
- expected: VARCHAR — ACC-xxxx
- missing (incl. disguised): **0** (0.0%) | distinct present: **3815**
- top values: 'ACC-8353'×6, 'ACC-3765'×6, 'ACC-2350'×5, 'ACC-9482'×5, 'ACC-5222'×5, 'ACC-4592'×5, 'ACC-1312'×4, 'ACC-6476'×4, 'ACC-6572'×4, 'ACC-9199'×4, 'ACC-8696'×4, 'ACC-3898'×4, 'ACC-8472'×4, 'ACC-5474'×4, 'ACC-3142'×4

### `account_name`
- expected: VARCHAR — free text, 1:1 with account_id
- missing (incl. disguised): **0** (0.0%) | distinct present: **200**
- top values: 'Hooli Co'×38, 'Tyrell Industries'×38, 'Prestige Labs'×37, 'Aperture Labs'×37, 'Vandelay Inc'×37, 'Globex LLC'×36, 'Stark Industries'×35, 'Stark Partners'×35, 'Wayne Ltd'×35, 'Oscorp Industries'×34, 'Hooli Partners'×34, 'Dunder LLC'×33, 'Cyberdyne Industries'×33, 'Hooli Holdings'×33, 'Oscorp Holdings'×32

### `contact_email`
- expected: VARCHAR — valid email; some _at_ for @
- missing (incl. disguised): **292** (5.7%) | distinct present: **40**
- top values: 'billing@oscorp.com'×254, 'billing@hooli.com'×253, 'billing@prestige.com'×248, 'billing@cyberdyne.com'×243, 'billing@gekko.com'×241, 'billing@aperture.com'×239, 'billing@stark.com'×239, 'billing@wayne.com'×238, 'billing@initech.com'×237, 'billing@vandelay.com'×237, 'billing@dunder.com'×236, 'billing@wonka.com'×231, 'billing@pied.com'×229, 'billing@globex.com'×228, 'billing@umbrella.com'×228
- VIOLATION — '_at_' instead of '@': count=142; samples=['billing_at_massive.com', 'billing_at_nakatomi.com', 'billing_at_pied.com']

### `region`
- expected: VARCHAR — NA / EMEA / APAC / LATAM
- missing (incl. disguised): **1288** (25.1%) | distinct present: **3**
- top values: 'EMEA'×1309, 'LATAM'×1264, 'APAC'×1264

### `industry`
- expected: VARCHAR — free text
- missing (incl. disguised): **422** (8.2%) | distinct present: **10**
- top values: 'Travel'×494, 'Manufacturing'×490, 'Education'×487, 'Healthcare'×485, 'Retail'×482, 'Gaming'×478, 'Media'×459, 'Energy'×452, 'Logistics'×442, 'Fintech'×434

### `plan`
- expected: VARCHAR — Starter / Pro / Enterprise
- missing (incl. disguised): **0** (0.0%) | distinct present: **18**
- top values: 'starter'×458, ' Starter '×444, 'Starter'×426, 'Tier 1'×408, 'STARTER'×406, 'Start'×403, 'Professional'×282, 'PRO'×277, 'pro'×271, 'Tier 2'×247, 'Pro'×244, 'Pro '×229, 'Enterprise'×183, 'enterprise '×177, 'Tier 3'×176
- VIOLATION — leading/trailing whitespace: count=1023; samples=[' Starter ', 'Enterprise ', 'Pro ']

### `billing_cycle`
- expected: VARCHAR — monthly / annual
- missing (incl. disguised): **0** (0.0%) | distinct present: **6**
- top values: 'Monthly'×1251, 'monthly'×1241, 'Annual'×687, 'annual'×684, 'annually'×636, 'yearly'×626

### `seats`
- expected: BIGINT — positive integer
- missing (incl. disguised): **0** (0.0%) | distinct present: **8**
- top values: '10'×1103, '5'×600, '1'×593, '100'×583, '250'×573, '3'×561, '25'×559, '50'×553

### `currency`
- expected: VARCHAR — USD / EUR / GBP
- missing (incl. disguised): **0** (0.0%) | distinct present: **3**
- top values: 'USD'×3559, 'EUR'×1080, 'GBP'×486

### `amount`
- expected: DOUBLE — numeric; negative if refunded
- missing (incl. disguised): **0** (0.0%) | distinct present: **1244**
- top values: '4900.00'×102, '490.00'×89, '990.00'×82, '12250.00'×80, '9900.00'×77, '2450.00'×68, '$4,900.00'×53, '29900.00'×49, '24750.00'×44, '49000.00'×43, '1470.00'×41, '1225.00'×40, '122500.00'×40, '24500.00'×39, '4950.00'×39
- VIOLATION — non-numeric: count=396; samples=['£28,003.50', '€529.20', '€5,292.00']
- VIOLATION — needs parsing ($ , currency-suffix): count=1683; samples=['$4,900.00', '$-4,900.00', '4,165.00 USD']

### `discount_pct`
- expected: DOUBLE — 0-100
- missing (incl. disguised): **0** (0.0%) | distinct present: **5**
- top values: '0'×3582, '10'×523, '15'×410, '20'×333, '25'×277

### `status`
- expected: VARCHAR — paid/pending/failed/refunded/void
- missing (incl. disguised): **0** (0.0%) | distinct present: **25**
- top values: 'completed'×600, 'Complete'×590, 'paid'×590, 'Paid'×586, 'PAID'×586, 'success'×564, 'PENDING'×110, 'in_review'×107, 'Pending'×105, 'pending'×97, 'awaiting'×94, 'REFUND'×94, 'declined'×91, 'cancelled'×90, 'FAILED'×86

### `payment_method`
- expected: VARCHAR — credit_card/ACH/wire/invoice
- missing (incl. disguised): **637** (12.4%) | distinct present: **7**
- top values: 'ACH'×672, 'credit_card'×662, 'Wire Transfer'×649, 'ach'×641, 'invoice'×639, 'Credit Card'×625, 'wire'×600

### `signup_date`
- expected: DATE — mixed date formats
- missing (incl. disguised): **0** (0.0%) | distinct present: **3147**
- top values: '2023-06-15'×8, '2024-03-18'×6, '03/31/2022'×6, '2021-06-23'×6, '2024-09-19'×6, '2024-08-31'×6, '2022-06-27'×6, '2023-12-08'×5, '2023-04-09'×5, '2024-08-08'×5, '2024-02-26'×5, '2024-08-27'×5, '2021-06-02'×5, '2021-12-29'×5, '2022-10-15'×5
- VIOLATION — date formats seen: count={'MM/DD/YYYY or DD/MM/YYYY (ambiguous)': 1259, 'YYYY-MM-DD': 2354, 'DD-MM-YYYY / MM-DD-YYYY (ambiguous)': 293, 'Mon D YYYY': 466, 'YYYY/MM/DD': 753}; samples=[]

### `invoice_date`
- expected: DATE — mixed date formats
- missing (incl. disguised): **0** (0.0%) | distinct present: **3528**
- top values: '2023-09-04'×7, '2024-04-30'×7, '2023-12-27'×6, '2023-08-02'×6, '2025-07-27'×6, '2024-04-07'×6, '2024-06-07'×6, '2024-02-13'×5, '2023-10-26'×5, '02/03/2023'×5, '2024-05-28'×5, '2023-03-09'×5, '2025-09-01'×5, '2024-03-11'×5, '2024-01-16'×5
- VIOLATION — date formats seen: count={'MM/DD/YYYY or DD/MM/YYYY (ambiguous)': 1320, 'YYYY-MM-DD': 2324, 'DD-MM-YYYY / MM-DD-YYYY (ambiguous)': 239, 'Mon D YYYY': 509, 'YYYY/MM/DD': 733}; samples=[]

### `churned`
- expected: BOOLEAN — true/TRUE/Yes/1/Y vs false/...
- missing (incl. disguised): **0** (0.0%) | distinct present: **10**
- top values: '0'×875, 'N'×837, 'FALSE'×818, 'false'×817, 'No'×788, 'TRUE'×211, 'Yes'×208, '1'×206, 'Y'×187, 'true'×178

### `csat_score`
- expected: BIGINT — 1-5
- missing (incl. disguised): **623** (12.2%) | distinct present: **5**
- top values: '5'×1411, '4'×1353, '3'×873, '2'×457, '1'×408

### `support_tickets`
- expected: BIGINT — non-negative integer
- missing (incl. disguised): **0** (0.0%) | distinct present: **6**
- top values: '0'×3062, '1'×749, '2'×520, '3'×358, '5'×270, '8'×166

## 3. Keys, uniqueness & duplicates

- Rows: 5125
- `invoice_id` distinct: 5000 → unique=False
- **Exact duplicate rows** (all cols): 163
- `invoice_id` appearing >1×: 124 ids, 249 rows total
- Among duplicated `invoice_id`, columns that disagree (near-dupes): {'status': 43}
  - `INV-100071` differs on ['status']: {'status': ['completed', 'paid']}
  - `INV-100152` differs on ['status']: {'status': ['completed', 'PAID']}
  - `INV-100362` differs on ['status']: {'status': ['completed', 'Complete']}

## 4. account_id ↔ account_name

- Distinct account_id: 3815 | distinct account_name: 200
- account_id with >1 name: 976 (trivial case/space: 0, genuine conflicts: 976)
  - `ACC-1000`: ['Gekko Co', 'Gekko Industries']
  - `ACC-1007`: ['Oscorp Ltd', 'Soylent Group']
- account_name mapping to >1 account_id: 200

## 5. Known data issues (from BUSINESS_CONTEXT)

| issue | status | evidence |
| --- | --- | --- |
| Inconsistent categories (plan/status/billing_cycle casings+spellings) | confirmed | plan=14 variants, status=25, billing_cycle=6 distinct |
| Mixed date formats | confirmed | see signup_date/invoice_date format breakdown above |
| Amounts as strings ($, commas, currency suffix, missing cents) | confirmed | 1683 amounts need parsing |
| Negative refund amounts | confirmed | 272 negative amounts |
| Nulls in contact_email | confirmed | 292 missing |
| Nulls in industry | confirmed | 422 missing |
| Nulls in csat_score | confirmed | 623 missing |
| Malformed emails (_at_) | confirmed | 142 rows |
| Full-duplicate rows | confirmed | 163 rows |
| Near-duplicate invoice_id (differing status/amount) | confirmed | 124 ids |
| Boolean variants in churned | confirmed | ['0', '1', 'FALSE', 'N', 'No', 'TRUE', 'Y', 'Yes', 'false', 'true'] |

## 6. Additional issues found (not in BUSINESS_CONTEXT)

- `payment_method` blank/disguised-null: 637 rows (BC says 'may be blank' but worth flagging).
- Invoice dates in 2026+ (future relative to a 2024/2025 book): ~609 rows — affects 'in 2024' filters.
- `discount_pct` outside 0–100: 0 rows.
- `seats` <= 0: 0 rows.
- `payment_method` casing/spelling variants: 8 distinct (e.g. 'Credit Card'/'credit_card').
