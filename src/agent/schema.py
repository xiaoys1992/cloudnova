"""Load schema.json (the pipeline contract) and render it for the prompt.

Column names are discovered here at runtime -- never hardcoded in agent code.
"""
from __future__ import annotations

import json
from pathlib import Path

from .errors import DataError


def load_schema(schema_path: Path) -> dict:
    if not Path(schema_path).exists():
        raise DataError(
            f"Schema not found at {schema_path}. Run `python -m app clean` first."
        )
    try:
        with Path(schema_path).open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        raise DataError(f"Could not read schema.json: {exc}") from exc


def column_names(schema: dict) -> set[str]:
    return {c["name"] for c in schema.get("columns", [])}


def render_schema(schema: dict) -> str:
    """Compact human/LLM-readable column listing used in the system prompt."""
    table = schema.get("table", "invoices")
    n = schema.get("row_count", "?")
    lines = [f"Table `{table}` ({n} rows). Columns:"]
    for c in schema.get("columns", []):
        parts = [f"- {c['name']} {c.get('type', '')}".rstrip()]
        if c.get("allowed_values"):
            parts.append("values=" + "/".join(map(str, c["allowed_values"])))
        if c.get("nullable"):
            parts.append("nullable")
        desc = c.get("description")
        line = "  ".join(parts)
        if desc:
            line += f" -- {desc}"
        lines.append(line)
    return "\n".join(lines)
