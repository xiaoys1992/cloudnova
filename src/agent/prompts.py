"""Runtime prompt assembly for NL->SQL, retry, and answer rendering.

Built fresh each call from schema.json + specs/metrics_spec.md + few-shots.
Nothing about the data (columns, constants) is hardcoded here.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .schema import column_names, render_schema

UNANSWERABLE = "UNANSWERABLE:"


def load_few_shots(path: Path, schema: dict) -> list[dict]:
    """Load few-shot examples, skipping any that need a column not in schema."""
    if not Path(path).exists():
        return []
    with Path(path).open("r", encoding="utf-8-sig") as fh:
        examples = yaml.safe_load(fh) or []
    cols = column_names(schema)
    kept = []
    for ex in examples:
        req = set(ex.get("requires") or [])
        if req <= cols:
            kept.append(ex)
    return kept


def build_nl2sql_system(schema: dict, metrics_md: str, few_shots: list[dict]) -> str:
    shots = "\n\n".join(
        f"Q: {ex['question']}\nSQL:\n{ex['sql'].strip()}" for ex in few_shots
    )
    shots_block = f"\n\nExamples (patterns to follow):\n\n{shots}" if shots else ""
    return f"""You translate a business question about CloudNova invoices into ONE DuckDB SQL query.

Rules:
- Query the single view `invoices`. Use ONLY the columns listed below (exact names).
- Output ONE read-only statement starting with SELECT or WITH. No prose, no markdown fences, no semicolon-separated statements, no DDL/DML.
- For any revenue / MRR / churn / refund / exposure / top-accounts question, follow the metric definitions in the METRICS SPEC exactly (status filters, time windows on invoice_date, per-account dedup via the latest invoice, refund netting, USD columns).
- Do not invent columns or business constants. All money is already in USD columns.
- If the question cannot be answered from these columns, or is too ambiguous to map to one query, respond with a single line `{UNANSWERABLE} <short reason>` and no SQL.

SCHEMA:
{render_schema(schema)}

METRICS SPEC (authoritative definitions):
{metrics_md}{shots_block}"""


def build_retry_user(question: str, failed_sql: str, error: str) -> str:
    return f"""The previous SQL for this question failed.

Question: {question}

Failed SQL:
{failed_sql}

DuckDB error:
{error}

Return ONE corrected read-only SELECT/WITH statement only. No prose, no fences."""


def build_answer_system() -> str:
    return (
        "You turn a SQL query result into ONE short plain-English paragraph for a "
        "finance stakeholder. Quote ONLY numbers that appear in the provided rows; "
        "never invent or extrapolate figures. State currency (USD) and units. "
        "Keep it to a few sentences. If the rows are empty, say no matching data "
        "was found."
    )


def build_answer_user(question: str, rows: list[dict]) -> str:
    import json

    preview = json.dumps(rows[:50], ensure_ascii=False, default=str)
    return f"Question: {question}\n\nResult rows (JSON):\n{preview}\n\nWrite the answer paragraph."
