"""Thin Anthropic wrapper. Isolated so the rest of the agent (and the tests)
import nothing that requires an API key or network.
"""
from __future__ import annotations

import os

from .errors import ConfigError, QueryError


def get_client():
    """Build an Anthropic client, or raise a clear ConfigError if no key."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file "
            "(see .env.example) or export it in your shell."
        )
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("The `anthropic` package is not installed.") from exc
    return Anthropic(api_key=key)


def _text(resp) -> str:
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def complete(client, model: str, system: str, user: str, max_tokens: int = 1024) -> str:
    """One non-streaming completion. Network/LLM failures -> QueryError."""
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _text(resp)
    except Exception as exc:  # noqa: BLE001
        raise QueryError(f"LLM request failed: {str(exc).splitlines()[0]}") from exc
