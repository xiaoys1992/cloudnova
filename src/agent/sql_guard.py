"""SQL guardrails: read-only, single-statement SELECT/WITH only.

Pure string validation -- no DB, no API -- so it is cheap and unit-testable.
"""
from __future__ import annotations

import re

from .errors import GuardrailError

# Statement keywords that must never appear anywhere in a read-only query.
_FORBIDDEN = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE", "MERGE", "ATTACH", "DETACH", "COPY", "PRAGMA", "INSTALL",
    "LOAD", "EXPORT", "IMPORT", "CALL", "SET", "RESET", "GRANT", "REVOKE",
    "VACUUM", "CHECKPOINT",
]
_FORBIDDEN_RE = re.compile(
    r"(?<![\w.])(" + "|".join(_FORBIDDEN) + r")(?![\w])", re.IGNORECASE
)
_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def clean_sql(raw: str) -> str:
    """Strip markdown fences / prose wrappers and a single trailing semicolon."""
    s = (raw or "").strip()
    if s.startswith("```"):
        # drop leading ```sql and trailing ```
        s = _FENCE_RE.sub("", s).strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    # keep only from the first SELECT/WITH if the model added a prose preamble
    m = re.search(r"\b(SELECT|WITH)\b", s, re.IGNORECASE)
    if m:
        s = s[m.start():].strip()
    s = s.rstrip(";").strip()
    return s


def validate(raw: str) -> str:
    """Return cleaned SQL if it is a single read-only SELECT/WITH, else raise."""
    s = clean_sql(raw)
    if not s:
        raise GuardrailError("No SQL was produced for this question.")
    if ";" in s:
        raise GuardrailError("Only a single SQL statement is allowed.")
    head = s.lstrip().lower()
    if not (head.startswith("select") or head.startswith("with")):
        raise GuardrailError("Only read-only SELECT/WITH queries are allowed.")
    bad = _FORBIDDEN_RE.search(s)
    if bad:
        raise GuardrailError(
            f"Only read-only SELECT/WITH queries are allowed "
            f"(found disallowed keyword '{bad.group(1).upper()}')."
        )
    return s
