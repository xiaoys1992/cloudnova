"""Independent test oracle for CloudNova (Track B, Session A).

This module computes the frozen expected values for the five eval cases in
`specs/eval_spec.md` *from scratch* using plain pandas over the cleaned parquet.

It deliberately does NOT import, read, or reuse any code under `src/` (neither
`src/pipeline` nor `src/agent`). Every metric here is re-implemented directly
from `specs/metrics_spec.md`, so it can serve as an independent check on the
pipeline + agent outputs.

Run:
    .venv/Scripts/python.exe evals/oracle.py
stdout is pure JSON mapping "E01".."E05" to expected values (null for E05);
a one-line note naming E02's winning region is printed to stderr.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# The file lives in evals/, so the repo root is its parent's parent.
PATH = Path(__file__).resolve().parent.parent / "data" / "clean" / "cleaned.parquet"

# Module-level holder so the __main__ block can report E02's winning region
# without recomputing.
_E02_WINNING_REGION: str | None = None


def _load() -> pd.DataFrame:
    """Load the cleaned invoice ledger (one row per invoice, 5000 rows)."""
    df = pd.read_parquet(PATH)
    # invoice_date may be stored as a date or datetime; normalize to pandas
    # datetime so comparisons and sorts behave consistently. NaT stays NaT
    # (null invoice_date falls outside every time window, per metrics_spec §8).
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    return df


def _latest_per_account(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce to one row per account_id = its latest invoice.

    Point-in-time rule (metrics_spec §2a / A4): order by invoice_date DESC,
    tie-break invoice_id DESC, keep the first row per account_id.
    """
    ranked = df.sort_values(
        by=["invoice_date", "invoice_id"],
        ascending=[False, False],
        kind="mergesort",  # stable
        na_position="last",  # null invoice_date never wins "latest"
    )
    return ranked.drop_duplicates(subset="account_id", keep="first")


def e01() -> float:
    """Recognized revenue in 2024.

    SUM(amount_usd) over status in ('paid','refunded') and invoice_date in
    [2024-01-01, 2025-01-01). Refunds (negative amount_usd) net against revenue.
    """
    df = _load()
    start = pd.Timestamp("2024-01-01")
    end = pd.Timestamp("2025-01-01")
    mask = (
        df["status"].isin(["paid", "refunded"])
        & (df["invoice_date"] >= start)
        & (df["invoice_date"] < end)
    )
    return float(df.loc[mask, "amount_usd"].sum())


def e02() -> float:
    """Region with the highest average MRR per account.

    One row per account (latest invoice); churned accounts contribute
    mrr_usd = 0; average current MRR by region; return the max region's average.
    """
    global _E02_WINNING_REGION
    df = _load()
    current = _latest_per_account(df).copy()
    current["current_mrr_usd"] = current["mrr_usd"].where(~current["churned"].fillna(False), 0.0)
    by_region = current.groupby("region", dropna=True)["current_mrr_usd"].mean()
    _E02_WINNING_REGION = str(by_region.idxmax())
    return float(by_region.max())


def e03() -> float:
    """Enterprise churn rate.

    One row per account (latest invoice); keep plan == 'Enterprise';
    return mean(churned) as a fraction in [0, 1].
    """
    df = _load()
    current = _latest_per_account(df)
    ent = current[current["plan"] == "Enterprise"]
    churned = ent["churned"].fillna(False).astype(float)
    return float(churned.mean())


def e04() -> float:
    """Total refunds given back, as a positive magnitude.

    -SUM(amount_usd) over status == 'refunded' (refund amounts are negative).
    """
    df = _load()
    return float(-df.loc[df["status"] == "refunded", "amount_usd"].sum())


def e05() -> None:
    """Monthly churn rate in 2024 — undefined, returns None.

    `churned` is a single cumulative, point-in-time boolean per account
    (metrics_spec A7) with no churn date. There is no way to attribute a churn
    event to a specific month or to 2024, so a proper period churn rate
    (churned-in-period / active-at-start) cannot be computed from this dataset.
    """
    return None


if __name__ == "__main__":
    results = {
        "E01": round(e01(), 2),
        "E02": round(e02(), 2),
        "E03": round(e03(), 4),
        "E04": round(e04(), 2),
        "E05": e05(),  # None -> JSON null
    }
    print(json.dumps(results))
    print(f"note: E02 winning region = {_E02_WINNING_REGION}", file=sys.stderr)
