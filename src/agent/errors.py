"""Typed errors for the query agent. All surface to users as one clear line."""
from __future__ import annotations


class AgentError(Exception):
    """Base class for agent errors."""


class ConfigError(AgentError):
    """Missing/invalid configuration (e.g. no ANTHROPIC_API_KEY)."""


class DataError(AgentError):
    """Cleaned data (cleaned.parquet / schema.json) missing or unreadable."""


class GuardrailError(AgentError):
    """Generated SQL violated the read-only single-statement allow-list."""


class QueryError(AgentError):
    """SQL failed to execute (parse/binding/runtime error or timeout)."""
