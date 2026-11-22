"""Entry point: python -m src.pipeline"""
from __future__ import annotations

import sys

from .clean import PipelineError, run


def main() -> int:
    try:
        result = run()
    except PipelineError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Cleaned {result['rows_in']} -> {result['rows_out']} rows "
          f"(removed {result['rows_in'] - result['rows_out']}).")
    print(f"Outputs in {result['clean_dir']}: cleaned.parquet, schema.json, cleaning_report.md")
    for r in result["rules"]:
        print(f"  {r['id']:4} {r['action']:8} {r['rows_affected']:>6}  {r['description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
