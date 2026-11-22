"""DuckDB access: register cleaned.parquet as view `invoices`, run queries
under a row cap and timeout. No API, no business logic.
"""
from __future__ import annotations

import datetime as dt
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from .errors import DataError, QueryError


def connect(parquet_path: Path) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB and expose the parquet as the view `invoices`."""
    if not Path(parquet_path).exists():
        raise DataError(
            f"Cleaned data not found at {parquet_path}. "
            f"Run `python -m app clean` first."
        )
    con = duckdb.connect(database=":memory:")
    safe = str(parquet_path).replace("'", "''")
    con.execute(f"CREATE VIEW invoices AS SELECT * FROM read_parquet('{safe}')")
    return con


def _jsonable(v: Any) -> Any:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def run_query(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    max_rows: int,
    timeout_s: float,
) -> tuple[list[dict], bool]:
    """Execute `sql`, capped at max_rows, under a wall-clock timeout.

    Returns (rows, truncated). Raises QueryError on failure/timeout.
    """
    # Wrap so the cap is enforced regardless of the model's own LIMIT.
    wrapped = f"SELECT * FROM (\n{sql}\n) AS _agent_q LIMIT {max_rows + 1}"
    box: dict[str, Any] = {}

    def _work() -> None:
        try:
            rel = con.execute(wrapped)
            cols = [d[0] for d in rel.description]
            box["rows"] = [
                {c: _jsonable(v) for c, v in zip(cols, row)}
                for row in rel.fetchall()
            ]
        except Exception as exc:  # noqa: BLE001 - surfaced as QueryError
            box["error"] = exc

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        try:
            con.interrupt()
        except Exception:  # noqa: BLE001
            pass
        t.join(1.0)
        raise QueryError(f"Query exceeded the {timeout_s}s timeout.")
    if "error" in box:
        raise QueryError(str(box["error"]).strip().splitlines()[0])

    rows = box.get("rows", [])
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    return rows, truncated
