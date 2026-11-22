"""Guardrail + row-limit tests. No API calls, no network -- pure SQL/DuckDB."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.agent import db, sql_guard
from src.agent.errors import GuardrailError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cleaned.parquet"


@pytest.mark.parametrize("bad", [
    "DROP TABLE invoices",
    "DELETE FROM invoices",
    "INSERT INTO invoices VALUES (1)",
    "UPDATE invoices SET seats = 0",
    "SELECT 1; DROP TABLE invoices",          # multiple statements
    "PRAGMA database_list",                     # non-SELECT
    "WITH x AS (SELECT 1) DELETE FROM invoices",  # DML behind a CTE
    "COPY invoices TO 'out.csv'",
    "",                                         # empty
])
def test_dangerous_sql_rejected(bad):
    with pytest.raises(GuardrailError):
        sql_guard.validate(bad)


@pytest.mark.parametrize("ok", [
    "SELECT COUNT(*) FROM invoices",
    "select sum(amount_usd) from invoices where status = 'paid'",
    "WITH r AS (SELECT * FROM invoices) SELECT region FROM r",
    "```sql\nSELECT 1 AS n\n```",               # markdown fences stripped
    "SELECT 1 AS n;",                            # trailing semicolon ok
])
def test_valid_select_allowed(ok):
    cleaned = sql_guard.validate(ok)
    assert cleaned.lower().startswith(("select", "with"))
    assert ";" not in cleaned


def test_forbidden_keyword_not_confused_by_column_name():
    # columns like `support_tickets`/`updated` must not trip the keyword scan
    assert sql_guard.validate("SELECT support_tickets FROM invoices")


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture parquet missing")
def test_row_limit_applied():
    con = db.connect(FIXTURE)
    rows, truncated = db.run_query(con, "SELECT * FROM invoices", max_rows=3,
                                   timeout_s=10)
    assert len(rows) == 3
    assert truncated is True


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture parquet missing")
def test_small_result_not_truncated():
    con = db.connect(FIXTURE)
    rows, truncated = db.run_query(con, "SELECT COUNT(*) AS n FROM invoices",
                                   max_rows=1000, timeout_s=10)
    assert rows == [{"n": 10}]
    assert truncated is False
