"""Orchestration: ask(question) -> {"answer", "sql", "rows"}.

Flow: load config + schema -> build prompt -> NL->SQL -> guardrail -> execute
(retry once on SQL error) -> summarize rows into a paragraph.

Design note on errors (reconciles query_agent_spec s1 and s7):
- Fatal preconditions (missing ANTHROPIC_API_KEY, missing cleaned data) RAISE
  ConfigError/DataError so the CLI can exit non-zero with one clear line (s7).
- In-flow handled failures (guardrail rejection, unanswerable, bad SQL after the
  single retry) RETURN the dict with an explanatory `answer` and rows=[] (s1).
"""
from __future__ import annotations

from . import db, llm, prompts
from .config import Config, load_config
from .errors import GuardrailError, QueryError
from .schema import load_schema
from . import sql_guard


def _render_rows_fallback(rows: list[dict]) -> str:
    if not rows:
        return "The query ran successfully but returned no matching rows."
    if len(rows) == 1 and len(rows[0]) == 1:
        (k, v), = rows[0].items()
        return f"Result: {k} = {v}."
    head = rows[0]
    cols = ", ".join(head.keys())
    return f"Returned {len(rows)} row(s) with columns: {cols}. See the rows for details."


def _result(answer: str, sql: str, rows: list[dict]) -> dict:
    return {"answer": answer, "sql": sql, "rows": rows}


def ask(question: str, config: Config | None = None) -> dict:
    cfg = config or load_config()
    question = (question or "").strip()
    if not question:
        return _result("Please provide a question to ask.", "", [])

    # Preconditions (raise -> CLI exits non-zero).
    schema = load_schema(cfg.schema_path)          # DataError if missing
    client = llm.get_client()                      # ConfigError if no API key
    con = db.connect(cfg.parquet_path)             # DataError if missing

    few_shots = prompts.load_few_shots(cfg.few_shots_path, schema)
    metrics_md = cfg.metrics_spec_path.read_text(encoding="utf-8-sig") \
        if cfg.metrics_spec_path.exists() else "(metrics spec unavailable)"
    system = prompts.build_nl2sql_system(schema, metrics_md, few_shots)

    # 1) Generate SQL.
    raw = llm.complete(client, cfg.model, system, question)
    if raw.strip().upper().startswith(prompts.UNANSWERABLE):
        reason = raw.split(":", 1)[1].strip() if ":" in raw else raw.strip()
        return _result(
            f"I can't answer that from the available data: {reason}", "", []
        )

    try:
        sql = sql_guard.validate(raw)
    except GuardrailError as exc:
        return _result(str(exc), sql_guard.clean_sql(raw), [])

    # 2) Execute, with one retry that feeds the error back to the model.
    try:
        rows, truncated = db.run_query(
            con, sql, cfg.max_rows, cfg.query_timeout_s
        )
    except QueryError as first_err:
        retry_user = prompts.build_retry_user(question, sql, str(first_err))
        raw2 = llm.complete(client, cfg.model, system, retry_user)
        try:
            sql = sql_guard.validate(raw2)
        except GuardrailError as exc:
            return _result(str(exc), sql_guard.clean_sql(raw2), [])
        try:
            rows, truncated = db.run_query(
                con, sql, cfg.max_rows, cfg.query_timeout_s
            )
        except QueryError as second_err:
            return _result(
                f"I couldn't run a valid query for that question ({second_err}).",
                sql,
                [],
            )

    # 3) Summarize rows into a paragraph (fall back to deterministic text).
    try:
        answer = llm.complete(
            client,
            cfg.model,
            prompts.build_answer_system(),
            prompts.build_answer_user(question, rows),
            max_tokens=400,
        )
        if not answer:
            answer = _render_rows_fallback(rows)
    except QueryError:
        answer = _render_rows_fallback(rows)

    if truncated:
        answer += (
            f" (Results truncated to the first {cfg.max_rows} rows; "
            f"refine the question for the full set.)"
        )
    return _result(answer, sql, rows)
