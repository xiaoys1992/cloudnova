"""Eval harness — python -m evals

Loads cases from evals/cases.yaml, asks the agent each question, and compares the
first numeric value in result["rows"] against the oracle's expected value within
tolerance. See specs/eval_spec.md.

Exit code: non-zero ONLY on an unexpected failure (a non-xfail case that FAILs).
Missing agent or missing cleaned data -> clear message, clean exit (0).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = Path(__file__).resolve().parent / "cases.yaml"
PARQUET = ROOT / "data" / "clean" / "cleaned.parquet"


def first_number(obj):
    """First numeric value found walking rows (dicts/lists/scalars). Skips bools."""
    if isinstance(obj, bool):
        return None
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, str):
        s = obj.replace(",", "").replace("$", "").strip().rstrip("%")
        try:
            return float(s)
        except ValueError:
            return None
    if isinstance(obj, dict):
        for v in obj.values():
            r = first_number(v)
            if r is not None:
                return r
    if isinstance(obj, (list, tuple)):
        for v in obj:
            r = first_number(v)
            if r is not None:
                return r
    return None


def within_tol(expected, got, tol) -> bool:
    if expected is None or got is None:
        return False
    kind, val = tol.get("type", "absolute"), float(tol.get("value", 0))
    if kind == "relative":
        denom = abs(expected) if expected else 1.0
        return abs(got - expected) <= val * denom
    return abs(got - expected) <= val


def fmt(x):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:,.4f}" if abs(x) < 10 else f"{x:,.2f}"
    return str(x)


def truncate(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "..."


def main() -> int:
    if not CASES_PATH.exists():
        print(f"ERROR: cases file not found: {CASES_PATH}\n"
              f"Generate it from evals/oracle.py first.", file=sys.stderr)
        return 0
    if not PARQUET.exists():
        print(f"ERROR: cleaned data not found: {PARQUET}\n"
              f"Run the pipeline first:  python -m src.pipeline", file=sys.stderr)
        return 0

    try:
        from src.agent import ask
    except Exception as e:  # noqa: BLE001 - import/config failures surface as one message
        print("ERROR: could not import the query agent (src.agent.ask).\n"
              f"Reason: {e}\n"
              "The agent (Session B) must expose ask(question)->{'answer','sql','rows'}.",
              file=sys.stderr)
        return 0

    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))["cases"]

    rows_out = []
    unexpected_failures = 0
    for c in cases:
        cid, q = c["id"], c["question"]
        expected, xfail = c.get("expected"), bool(c.get("xfail", False))
        tol = c.get("tolerance", {"type": "absolute", "value": 0})
        got, sql, err = None, "", None
        try:
            res = ask(q)
            got = first_number(res.get("rows"))
            sql = res.get("sql", "") or ""
        except Exception as e:  # noqa: BLE001 - per-case failure, keep going
            err = str(e)

        if xfail:
            status = "XFAIL"
        elif err is not None:
            status, unexpected_failures = "FAIL", unexpected_failures + 1
        elif within_tol(expected, got, tol):
            status = "PASS"
        else:
            status, unexpected_failures = "FAIL", unexpected_failures + 1

        rows_out.append((cid, q, expected, got, status, sql, err))

    # Table.
    print(f"\nEval: {len(cases)} cases  |  data={PARQUET.name}\n")
    header = f"{'id':<4} {'expected':>14} {'got':>14}  {'status':<6} question / sql"
    print(header)
    print("-" * len(header))
    for cid, q, expected, got, status, sql, err in rows_out:
        print(f"{cid:<4} {fmt(expected):>14} {fmt(got):>14}  {status:<6} {truncate(q, 60)}")
        if sql:
            print(f"{'':<42}sql: {truncate(sql, 90)}")
        if err:
            print(f"{'':<42}err: {truncate(err, 90)}")

    passed = sum(1 for r in rows_out if r[4] == "PASS")
    xf = sum(1 for r in rows_out if r[4] == "XFAIL")
    print(f"\n{passed} PASS, {unexpected_failures} FAIL, {xf} XFAIL")
    if unexpected_failures:
        print("Unexpected failures present -> non-zero exit.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
