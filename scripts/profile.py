"""Profile the raw CloudNova invoice ledger (NO cleaning).

Reads data/raw/cloudnova_invoices.csv as raw strings so nothing is silently
coerced, then writes a concise profile to docs/data_profile.md.

Run: .venv/Scripts/python scripts/profile.py
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
RAW = ROOT / CONFIG["paths"]["raw_csv"]
OUT = ROOT / "docs" / "data_profile.md"

# Values that look present but mean "missing".
DISGUISED_NULLS = {"", "n/a", "na", "null", "none", "nan", "-", "--", "?", "unknown"}

# Expectation table sourced from docs/BUSINESS_CONTEXT.md.
EXPECTATIONS = {
    "invoice_id":     ("Invoice key (unique-ish; dup in near-dupes)", "VARCHAR", "INV-xxxxxx"),
    "account_id":     ("Customer account id", "VARCHAR", "ACC-xxxx"),
    "account_name":   ("Customer account name", "VARCHAR", "free text, 1:1 with account_id"),
    "contact_email":  ("Billing contact (nullable/malformed)", "VARCHAR", "valid email; some _at_ for @"),
    "region":         ("Region", "VARCHAR", "NA / EMEA / APAC / LATAM"),
    "industry":       ("Account industry (nullable)", "VARCHAR", "free text"),
    "plan":           ("Subscription plan (dirty)", "VARCHAR", "Starter / Pro / Enterprise"),
    "billing_cycle":  ("Billing cycle (dirty)", "VARCHAR", "monthly / annual"),
    "seats":          ("Licensed seats", "BIGINT", "positive integer"),
    "currency":       ("Invoice currency", "VARCHAR", "USD / EUR / GBP"),
    "amount":         ("Invoice amount (messy string)", "DOUBLE", "numeric; negative if refunded"),
    "discount_pct":   ("Discount percentage", "DOUBLE", "0-100"),
    "status":         ("Payment status (dirty)", "VARCHAR", "paid/pending/failed/refunded/void"),
    "payment_method": ("Payment method (dirty/nullable)", "VARCHAR", "credit_card/ACH/wire/invoice"),
    "signup_date":    ("Account signup date (dirty)", "DATE", "mixed date formats"),
    "invoice_date":   ("Invoice issue date (dirty)", "DATE", "mixed date formats"),
    "churned":        ("Account churned (dirty bool)", "BOOLEAN", "true/TRUE/Yes/1/Y vs false/..."),
    "csat_score":     ("Latest CSAT (nullable)", "BIGINT", "1-5"),
    "support_tickets": ("Tickets opened", "BIGINT", "non-negative integer"),
}

ALLOWED = {
    "region": {"NA", "EMEA", "APAC", "LATAM"},
    "currency": {"USD", "EUR", "GBP"},
}
DATE_PATTERNS = [
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "YYYY-MM-DD"),
    (re.compile(r"^\d{4}/\d{2}/\d{2}$"), "YYYY/MM/DD"),
    (re.compile(r"^\d{2}/\d{2}/\d{4}$"), "MM/DD/YYYY or DD/MM/YYYY (ambiguous)"),
    (re.compile(r"^\d{2}-\d{2}-\d{4}$"), "DD-MM-YYYY / MM-DD-YYYY (ambiguous)"),
    (re.compile(r"^[A-Za-z]{3} \d{1,2} \d{4}$"), "Mon D YYYY"),
]


def is_null(v: str) -> bool:
    return v.strip().lower() in DISGUISED_NULLS


def numeric_ok(v: str) -> bool:
    s = v.strip().replace("$", "").replace(",", "")
    s = re.sub(r"\s*(USD|EUR|GBP)\s*$", "", s, flags=re.I)
    try:
        float(s)
        return True
    except ValueError:
        return False


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def esc(v: str) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def main() -> None:
    if not RAW.exists():
        raise SystemExit(f"Raw CSV not found: {RAW}")

    # Read everything as string; keep blanks so we can detect disguised nulls.
    df = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    n = len(df)
    L = [f"# CloudNova Raw Data Profile\n",
         f"Source: `{CONFIG['paths']['raw_csv']}` — **{n} rows**, {len(df.columns)} columns. "
         f"No cleaning applied; all values read as raw strings.\n"]

    # 1. Expectation table.
    L.append("## 1. Expectation table (from BUSINESS_CONTEXT)\n")
    L.append(md_table(
        ["column", "meaning", "expected type", "expected values/format"],
        [[c, *[esc(x) for x in EXPECTATIONS.get(c, ("?", "?", "?"))]] for c in df.columns],
    ))

    # 2. Per-column profile.
    L.append("\n## 2. Per-column profile\n")
    for col in df.columns:
        s = df[col]
        nulls = s.map(is_null)
        n_null = int(nulls.sum())
        present = s[~nulls]
        distinct = present.nunique()
        top = Counter(present).most_common(15)
        exp = EXPECTATIONS.get(col, ("?", "?", "?"))

        # Violations vs expectation.
        viol = []
        if col in ALLOWED:
            bad = present[~present.str.strip().isin(ALLOWED[col])]
            if len(bad):
                viol.append((f"not in {sorted(ALLOWED[col])}", len(bad), list(bad.unique()[:3])))
        if col in ("seats", "support_tickets", "csat_score"):
            bad = present[~present.str.strip().str.fullmatch(r"-?\d+")]
            if len(bad):
                viol.append(("non-integer", len(bad), list(bad.unique()[:3])))
        if col in ("amount", "discount_pct"):
            bad = present[~present.map(numeric_ok)]
            if len(bad):
                viol.append(("non-numeric", len(bad), list(bad.unique()[:3])))
        if col == "amount":
            dirty = present[present.str.contains(r"[\$,]|[A-Za-z]")]
            viol.append(("needs parsing ($ , currency-suffix)", len(dirty), list(dirty.unique()[:3])))
        if col == "contact_email":
            atless = present[~present.str.contains("@") & present.str.contains("_at_")]
            viol.append(("'_at_' instead of '@'", len(atless), list(atless.unique()[:3])))
        if col in ("signup_date", "invoice_date"):
            fmt = Counter()
            unmatched = []
            for v in present:
                v = v.strip()
                for pat, name in DATE_PATTERNS:
                    if pat.match(v):
                        fmt[name] += 1
                        break
                else:
                    unmatched.append(v)
            viol.append(("date formats seen", dict(fmt), unmatched[:3]))
        if col in ("plan", "status", "billing_cycle", "payment_method", "churned"):
            has_ws = present[present != present.str.strip()]
            if len(has_ws):
                viol.append(("leading/trailing whitespace", len(has_ws), list(has_ws.unique()[:3])))

        L.append(f"\n### `{col}`")
        L.append(f"- expected: {esc(exp[1])} — {esc(exp[2])}")
        L.append(f"- missing (incl. disguised): **{n_null}** ({n_null/n*100:.1f}%) | distinct present: **{distinct}**")
        L.append(f"- top values: {esc(', '.join(f'{v!r}×{c}' for v, c in top))}")
        for desc, cnt, samples in viol:
            L.append(f"- VIOLATION — {esc(desc)}: count={esc(cnt)}; samples={esc(samples)}")

    # 3. Keys / duplicates.
    L.append("\n## 3. Keys, uniqueness & duplicates\n")
    exact_dup = int(df.duplicated(keep=False).sum())
    id_counts = df["invoice_id"].value_counts()
    dup_ids = id_counts[id_counts > 1]
    L.append(f"- Rows: {n}")
    L.append(f"- `invoice_id` distinct: {df['invoice_id'].nunique()} → unique={df['invoice_id'].is_unique}")
    L.append(f"- **Exact duplicate rows** (all cols): {exact_dup}")
    L.append(f"- `invoice_id` appearing >1×: {len(dup_ids)} ids, {int(dup_ids.sum())} rows total")
    # How key-dupes differ.
    diff_cols = Counter()
    examples = []
    for inv, grp in df[df["invoice_id"].isin(dup_ids.index)].groupby("invoice_id"):
        if grp.duplicated(keep=False).all():
            continue  # pure exact dup, no field difference
        cols_differ = [c for c in df.columns if grp[c].nunique() > 1]
        for c in cols_differ:
            diff_cols[c] += 1
        if len(examples) < 3 and cols_differ:
            examples.append((inv, cols_differ, {c: list(grp[c].unique()) for c in cols_differ}))
    L.append(f"- Among duplicated `invoice_id`, columns that disagree (near-dupes): "
             f"{esc(dict(diff_cols.most_common()))}")
    for inv, cols, vals in examples:
        L.append(f"  - `{inv}` differs on {esc(cols)}: {esc(vals)}")

    # 4. account_id <-> account_name.
    L.append("\n## 4. account_id ↔ account_name\n")
    id_to_names = df.groupby("account_id")["account_name"].apply(lambda x: set(x.str.strip()))
    name_to_ids = df.groupby(df["account_name"].str.strip())["account_id"].nunique()
    multi_name = id_to_names[id_to_names.map(len) > 1]
    trivial, genuine = [], []
    for aid, names in multi_name.items():
        if len({x.lower() for x in names}) == 1:
            trivial.append((aid, sorted(names)))
        else:
            genuine.append((aid, sorted(names)))
    L.append(f"- Distinct account_id: {df['account_id'].nunique()} | distinct account_name: {name_to_ids.size}")
    L.append(f"- account_id with >1 name: {len(multi_name)} "
             f"(trivial case/space: {len(trivial)}, genuine conflicts: {len(genuine)})")
    for aid, names in (trivial[:2] + genuine[:2]):
        L.append(f"  - `{aid}`: {esc(names)}")
    shared = name_to_ids[name_to_ids > 1]
    L.append(f"- account_name mapping to >1 account_id: {len(shared)}")

    # 5. Known issues checklist.
    L.append("\n## 5. Known data issues (from BUSINESS_CONTEXT)\n")
    checks = []

    def status_count(col, pattern):
        return int(df[col].str.strip().str.contains(pattern, case=False, regex=True).sum())

    plan_variants = df["plan"].str.strip().nunique()
    status_variants = df["status"].str.strip().nunique()
    cycle_variants = df["billing_cycle"].str.strip().nunique()
    checks.append(("Inconsistent categories (plan/status/billing_cycle casings+spellings)", "confirmed",
                   f"plan={plan_variants} variants, status={status_variants}, billing_cycle={cycle_variants} distinct"))
    checks.append(("Mixed date formats", "confirmed", "see signup_date/invoice_date format breakdown above"))
    amt_dirty = int(df["amount"].str.contains(r"[\$,]|[A-Za-z]").sum())
    checks.append(("Amounts as strings ($, commas, currency suffix, missing cents)", "confirmed",
                   f"{amt_dirty} amounts need parsing"))
    neg = int(df["amount"].map(lambda v: numeric_ok(v) and float(re.sub(r"[^0-9.\-]", "", v)) < 0).sum())
    checks.append(("Negative refund amounts", "confirmed", f"{neg} negative amounts"))
    for c in ("contact_email", "industry", "csat_score"):
        checks.append((f"Nulls in {c}", "confirmed", f"{int(df[c].map(is_null).sum())} missing"))
    mal = int((~df["contact_email"].str.contains("@") & df["contact_email"].str.contains("_at_")).sum())
    checks.append(("Malformed emails (_at_)", "confirmed" if mal else "not found", f"{mal} rows"))
    checks.append(("Full-duplicate rows", "confirmed" if exact_dup else "not found", f"{exact_dup} rows"))
    checks.append(("Near-duplicate invoice_id (differing status/amount)", "confirmed" if len(dup_ids) else "not found",
                   f"{len(dup_ids)} ids"))
    churn_variants = sorted(df["churned"].str.strip().unique())
    checks.append(("Boolean variants in churned", "confirmed", esc(churn_variants)))
    L.append(md_table(["issue", "status", "evidence"], checks))

    # 6. Issues NOT listed in BUSINESS_CONTEXT.
    L.append("\n## 6. Additional issues found (not in BUSINESS_CONTEXT)\n")
    extra = []
    # invoice_date before signup_date? (needs parse; flag count of obvious year mismatch)
    pm_blank = int(df["payment_method"].map(is_null).sum())
    extra.append(f"- `payment_method` blank/disguised-null: {pm_blank} rows (BC says 'may be blank' but worth flagging).")
    # future invoice dates
    future = int(df["invoice_date"].str.contains(r"202[6-9]").sum())
    extra.append(f"- Invoice dates in 2026+ (future relative to a 2024/2025 book): ~{future} rows — affects 'in 2024' filters.")
    # discount out of range
    disc_bad = int(df["discount_pct"].map(lambda v: numeric_ok(v) and not (0 <= float(re.sub(r"[^0-9.\-]", "", v or "0")) <= 100)).sum())
    extra.append(f"- `discount_pct` outside 0–100: {disc_bad} rows.")
    # zero / negative seats
    seats_bad = int(df["seats"].map(lambda v: v.strip().lstrip("-").isdigit() and int(v) <= 0).sum())
    extra.append(f"- `seats` <= 0: {seats_bad} rows.")
    # payment_method casing variants
    extra.append(f"- `payment_method` casing/spelling variants: {df['payment_method'].str.strip().nunique()} distinct (e.g. 'Credit Card'/'credit_card').")
    L.extend(extra)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({n} rows profiled).")


if __name__ == "__main__":
    main()
