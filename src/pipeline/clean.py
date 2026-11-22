"""CloudNova cleaning pipeline — generated from specs/cleaning_spec.md.

One function per rule (named by rule ID), applied in spec §9 order. Each rule
returns (df, rows_affected) so cleaning_report.md and schema.json carry real
counts. All business constants come from config.yaml (never hardcoded here).

Run: python -m src.pipeline
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.yaml"

RAW_COLUMNS = [
    "invoice_id", "account_id", "account_name", "contact_email", "region",
    "industry", "plan", "billing_cycle", "seats", "currency", "amount",
    "discount_pct", "status", "payment_method", "signup_date", "invoice_date",
    "churned", "csat_score", "support_tickets",
]

DISGUISED_NULLS = {"", "n/a", "na", "null", "none", "nan", "-", "--", "?", "unknown"}

PLAN_KEYWORDS = [
    ("Starter", ("starter", "start", "tier 1")),
    ("Pro", ("professional", "pro", "tier 2")),      # 'professional' before 'pro'
    ("Enterprise", ("enterprise", "ent", "tier 3")),
]
STATUS_MAP = {
    "paid": "paid", "complete": "paid", "completed": "paid", "success": "paid",
    "pending": "pending", "in_review": "pending", "awaiting": "pending",
    "failed": "failed", "declined": "failed", "error": "failed",
    "refunded": "refunded", "refund": "refunded", "charged_back": "refunded",
    "void": "void", "cancelled": "void", "canceled": "void",
}
BILLING_MAP = {
    "monthly": "monthly",
    "annual": "annual", "annually": "annual", "yearly": "annual",
}
PAYMENT_MAP = {
    "credit_card": "credit_card", "credit card": "credit_card",
    "ach": "ACH",
    "wire": "wire", "wire transfer": "wire",
    "invoice": "invoice",
}
CHURN_TRUE = {"true", "yes", "1", "y"}
CHURN_FALSE = {"false", "no", "0", "n"}
STATUS_PRIORITY = {"paid": 5, "refunded": 4, "failed": 3, "pending": 2, "void": 1}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


class PipelineError(Exception):
    """Raised for user-facing, no-stack-trace failures."""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _clean_cell(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    s = re.sub(r"\s+", " ", s)
    return None if s.lower() in DISGUISED_NULLS else s


def _changed(before: pd.Series, after: pd.Series) -> int:
    """Count rows where value changed (NaN==NaN treated as equal)."""
    b = before.where(before.notna(), None)
    a = after.where(after.notna(), None)
    return int((b.astype(object) != a.astype(object)).sum())


def parse_amount(s):
    if s is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(s))
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(s):
    """Return datetime.date or None, per cleaning_spec §5."""
    if s is None:
        return None
    s = str(s).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)           # ISO
    if m:
        return _safe_date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", s)           # year-first slash
    if m:
        return _safe_date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^([A-Za-z]{3}) (\d{1,2}),? (\d{4})$", s)     # Mon D YYYY
    if m and m[1].lower() in MONTHS:
        return _safe_date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)     # ambiguous numeric
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        if a > 12:            # day-first forced
            return _safe_date(y, b, a)
        if b > 12:            # month-first forced
            return _safe_date(y, a, b)
        return _safe_date(y, a, b)   # default month-first (ASSUMPTION A-DATE)
    return None


def _safe_date(y, mo, d):
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# rules  (each: df -> (df, rows_affected))
# --------------------------------------------------------------------------- #
def r01_whitespace_nulls(df, cfg):
    obj = df.columns
    before = df.copy()
    for c in obj:
        df[c] = df[c].map(_clean_cell)
    affected = int((before.astype(object).where(before.notna(), None)
                    != df.astype(object).where(df.notna(), None)).any(axis=1).sum())
    return df, affected


def r02_normalize_plan(df, cfg):
    before = df["plan"].copy()

    def norm(v):
        if not isinstance(v, str):
            return None
        low = v.lower()
        for canon, keys in PLAN_KEYWORDS:
            if any(k in low for k in keys):
                return canon
        return None
    df["plan"] = df["plan"].map(norm)
    return df, _changed(before, df["plan"])


def r03_normalize_status(df, cfg):
    before = df["status"].copy()
    df["status"] = df["status"].map(lambda v: STATUS_MAP.get(v.lower()) if isinstance(v, str) else None)
    return df, _changed(before, df["status"])


def r04_normalize_billing_cycle(df, cfg):
    before = df["billing_cycle"].copy()
    df["billing_cycle"] = df["billing_cycle"].map(lambda v: BILLING_MAP.get(v.lower()) if isinstance(v, str) else None)
    return df, _changed(before, df["billing_cycle"])


def r05_normalize_payment_method(df, cfg):
    before = df["payment_method"].copy()
    df["payment_method"] = df["payment_method"].map(
        lambda v: PAYMENT_MAP.get(v.lower()) if isinstance(v, str) else None)
    return df, _changed(before, df["payment_method"])


def r06_churned_boolean(df, cfg):
    before = df["churned"].copy()

    def to_bool(v):
        if not isinstance(v, str):
            return None
        low = v.lower()
        if low in CHURN_TRUE:
            return True
        if low in CHURN_FALSE:
            return False
        return None
    df["churned"] = df["churned"].map(to_bool).astype("boolean")
    return df, _changed(before, df["churned"])


def r12_cast_numerics(df, cfg):
    affected = 0
    df["seats"] = pd.to_numeric(df["seats"], errors="coerce").astype("Int64")
    df["support_tickets"] = pd.to_numeric(df["support_tickets"], errors="coerce").astype("Int64")
    df["csat_score"] = pd.to_numeric(df["csat_score"], errors="coerce").astype("float64")
    before_disc = df["discount_pct"].copy()
    df["discount_pct"] = pd.to_numeric(df["discount_pct"], errors="coerce").astype("float64")
    affected = int(df[["seats", "support_tickets", "csat_score", "discount_pct"]].notna().any(axis=1).sum())
    _ = before_disc
    return df, affected


def r07_parse_amount(df, cfg):
    before_dirty = df["amount"].map(lambda v: bool(v) and bool(re.search(r"[^0-9.\-]", str(v))))
    df["amount_local"] = df["amount"].map(parse_amount)
    return df, int(before_dirty.sum())


def r08_fx_to_usd(df, cfg):
    fx = cfg["pipeline"]["fx_rates_to_usd"]

    def convert(row):
        amt, cur = row["amount_local"], row["currency"]
        if amt is None or pd.isna(amt) or cur not in fx:
            return None
        return amt / fx[cur]       # DIVIDE — ASSUMPTION A-FX
    df["amount_usd"] = df.apply(convert, axis=1).astype("float64")
    affected = int(df["amount_usd"].notna().sum())
    df = df.drop(columns=["amount", "amount_local"])
    return df, affected


def r09_derive_mrr(df, cfg):
    lp = cfg["pipeline"]["list_price_usd"]

    def mrr(row):
        plan, seats, disc = row["plan"], row["seats"], row["discount_pct"]
        if plan not in lp or pd.isna(seats) or pd.isna(disc):
            return None
        return lp[plan] * int(seats) * (1 - disc / 100.0)
    df["mrr_usd"] = df.apply(mrr, axis=1).astype("float64")
    return df, int(df["mrr_usd"].notna().sum())


def r10_parse_dates(df, cfg):
    affected = 0
    for col in ("signup_date", "invoice_date"):
        before_present = df[col].notna()
        df[col] = df[col].map(parse_date)
        affected += int(before_present.sum())
    return df, affected


def r11_fix_emails(df, cfg):
    before = df["contact_email"].copy()

    def fix(v):
        if not isinstance(v, str):
            return None
        v = v.replace("_at_", "@")
        return v if EMAIL_RE.match(v) else None
    df["contact_email"] = df["contact_email"].map(fix)
    return df, _changed(before, df["contact_email"])


def r13_drop_exact_duplicates(df, cfg):
    before = len(df)
    df = df.drop_duplicates(keep="first").reset_index(drop=True)
    return df, before - len(df)


def r14_resolve_id_collisions(df, cfg):
    before = len(df)
    df["_prio"] = df["status"].map(lambda s: STATUS_PRIORITY.get(s, 0))
    df["_absamt"] = df["amount_usd"].abs().fillna(-1)
    df["_order"] = range(len(df))
    df = (df.sort_values(["invoice_id", "_prio", "_absamt", "_order"],
                         ascending=[True, False, False, True])
            .drop_duplicates(subset=["invoice_id"], keep="first")
            .sort_values("_order")
            .drop(columns=["_prio", "_absamt", "_order"])
            .reset_index(drop=True))
    return df, before - len(df)


def r16_date_sanity(df, cfg):
    as_of = _as_of(cfg)
    low = dt.date(2015, 1, 1)

    def bad(row):
        iv, su = row["invoice_date"], row["signup_date"]
        if iv is None:
            return False
        if iv > as_of or iv < low:
            return True
        if su is not None and iv < su:
            return True
        return False
    return df, int(df.apply(bad, axis=1).sum())


def r17_flag_null_invoice_date(df, cfg):
    return df, int(df["invoice_date"].isna().sum())


RULES: list[tuple[str, str, str, Callable]] = [
    ("R01", "trim/collapse whitespace, disguised nulls -> NULL", "modified", r01_whitespace_nulls),
    ("R02", "normalize plan -> Starter/Pro/Enterprise", "modified", r02_normalize_plan),
    ("R03", "normalize status -> canonical 5", "modified", r03_normalize_status),
    ("R04", "normalize billing_cycle -> monthly/annual", "modified", r04_normalize_billing_cycle),
    ("R05", "normalize payment_method; blank -> NULL", "modified", r05_normalize_payment_method),
    ("R06", "churned -> BOOLEAN", "modified", r06_churned_boolean),
    ("R12", "cast numerics (seats, support_tickets, csat, discount)", "modified", r12_cast_numerics),
    ("R07", "parse amount string -> signed numeric (local)", "modified", r07_parse_amount),
    ("R08", "FX convert local -> amount_usd (divide by rate)", "modified", r08_fx_to_usd),
    ("R09", "derive mrr_usd = list*seats*(1-disc/100)", "added", r09_derive_mrr),
    ("R10", "parse signup_date/invoice_date; ambiguous = month-first", "modified", r10_parse_dates),
    ("R11", "fix _at_->@; invalid email -> NULL", "modified", r11_fix_emails),
    ("R13", "drop exact-duplicate rows", "dropped", r13_drop_exact_duplicates),
    ("R14", "resolve invoice_id collisions (status priority)", "dropped", r14_resolve_id_collisions),
    ("R16", "date sanity flag (future/pre-2015/invoice<signup)", "flagged", r16_date_sanity),
    ("R17", "flag null invoice_date (excluded from time windows)", "flagged", r17_flag_null_invoice_date),
]

# Output column order + metadata for schema.json (matches cleaning_spec §1).
COLUMN_META = [
    ("invoice_id", "VARCHAR", False, "Invoice key, unique after dedup.", None, ["R01", "R13", "R14"]),
    ("account_id", "VARCHAR", False, "Customer account key (authoritative).", None, ["R01"]),
    ("account_name", "VARCHAR", True, "Account display name; NOT a key (see A-ACCT).", None, ["R01"]),
    ("contact_email", "VARCHAR", True, "Billing email; _at_ fixed, invalid -> NULL.", None, ["R01", "R11"]),
    ("region", "VARCHAR", True, "Sales region.", ["NA", "EMEA", "APAC", "LATAM"], ["R01"]),
    ("industry", "VARCHAR", True, "Account industry.", None, ["R01"]),
    ("plan", "VARCHAR", False, "Subscription plan.", ["Starter", "Pro", "Enterprise"], ["R01", "R02"]),
    ("billing_cycle", "VARCHAR", False, "Billing cycle.", ["monthly", "annual"], ["R01", "R04"]),
    ("seats", "BIGINT", False, "Licensed seats.", None, ["R12"]),
    ("currency", "VARCHAR", False, "Invoice currency.", ["USD", "EUR", "GBP"], ["R01"]),
    ("amount_usd", "DOUBLE", True, "As-billed amount, FX->USD, signed (refunds<0).", None, ["R07", "R08"]),
    ("discount_pct", "DOUBLE", False, "Discount percent 0-100.", None, ["R12"]),
    ("status", "VARCHAR", False, "Payment status.", ["paid", "pending", "failed", "refunded", "void"], ["R01", "R03"]),
    ("payment_method", "VARCHAR", True, "Payment method; blank -> NULL.", ["credit_card", "ACH", "wire", "invoice"], ["R01", "R05"]),
    ("signup_date", "DATE", True, "Account signup date.", None, ["R10"]),
    ("invoice_date", "DATE", True, "Invoice issue date; drives time windows.", None, ["R10", "R16", "R17"]),
    ("churned", "BOOLEAN", False, "Account has since churned.", None, ["R06"]),
    ("csat_score", "DOUBLE", True, "Latest CSAT 1-5.", None, ["R12"]),
    ("support_tickets", "BIGINT", False, "Tickets opened.", None, ["R12"]),
    ("mrr_usd", "DOUBLE", False, "Derived monthly recurring revenue, USD.", None, ["R09"]),
]
OUTPUT_ORDER = [c[0] for c in COLUMN_META]


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def _as_of(cfg) -> dt.date:
    v = cfg["pipeline"]["as_of_date"]
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise PipelineError(f"Config not found: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def run() -> dict:
    cfg = load_config()
    raw = ROOT / cfg["paths"]["raw_csv"]
    clean_dir = ROOT / cfg["paths"]["clean_dir"]
    if not raw.exists():
        raise PipelineError(f"Raw CSV not found: {raw}\nExpected at config paths.raw_csv.")

    df = pd.read_csv(raw, dtype=str, keep_default_na=False)
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise PipelineError(f"Raw CSV missing required column(s): {', '.join(missing)}")

    rows_in = len(df)
    rule_counts: list[dict] = []
    for rid, desc, action, fn in RULES:
        df, affected = fn(df, cfg)
        rule_counts.append({"id": rid, "description": desc, "action": action,
                            "rows_affected": int(affected)})

    df = df[OUTPUT_ORDER]
    rows_out = len(df)

    # account_id<->account_name inconsistency (reported, not fixed; A-ACCT).
    multi_name = df.groupby("account_id")["account_name"].nunique()
    acct_conflicts = int((multi_name > 1).sum())

    clean_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(clean_dir / "cleaned.parquet", index=False)
    _write_schema(clean_dir / "schema.json", rows_out, rule_counts)
    _write_report(clean_dir / "cleaning_report.md", rows_in, rows_out, rule_counts, df, acct_conflicts)

    return {"rows_in": rows_in, "rows_out": rows_out, "rules": rule_counts,
            "acct_conflicts": acct_conflicts, "clean_dir": str(clean_dir)}


def _write_schema(path, row_count, rule_counts):
    schema = {
        "table": "invoices",
        "row_count": row_count,
        "columns": [
            {"name": n, "type": t, "nullable": nul, "description": d,
             "allowed_values": av, "rules_applied": ra}
            for (n, t, nul, d, av, ra) in COLUMN_META
        ],
        "rules": rule_counts,
    }
    path.write_text(json.dumps(schema, indent=2), encoding="utf-8")


def _write_report(path, rows_in, rows_out, rule_counts, df, acct_conflicts):
    lines = [
        "# CloudNova Cleaning Report\n",
        f"- **Rows in:** {rows_in}",
        f"- **Rows out:** {rows_out}  (removed {rows_in - rows_out} by R13+R14)",
        f"- **Unique invoice_id:** {df['invoice_id'].nunique()} (== rows_out: {df['invoice_id'].nunique() == rows_out})",
        "",
        "## Rows affected per rule\n",
        "| ID | action | rows_affected | description |",
        "| --- | --- | --- | --- |",
    ]
    for r in rule_counts:
        lines.append(f"| {r['id']} | {r['action']} | {r['rows_affected']} | {r['description']} |")

    paid = df[df["status"].isin(["paid", "refunded"])]["amount_usd"].sum()
    refunds = -df[df["status"] == "refunded"]["amount_usd"].sum()
    lines += [
        "",
        "## Post-clean sanity\n",
        f"- status breakdown: {df['status'].value_counts(dropna=False).to_dict()}",
        f"- plan breakdown: {df['plan'].value_counts(dropna=False).to_dict()}",
        f"- recognized revenue (paid+refunded, all-time USD): {paid:,.2f}",
        f"- refunds given back (USD): {refunds:,.2f}",
        f"- null amount_usd: {int(df['amount_usd'].isna().sum())} | null invoice_date: {int(df['invoice_date'].isna().sum())}",
        f"- account_id values carrying >1 account_name (A-ACCT, flagged not fixed): {acct_conflicts}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
