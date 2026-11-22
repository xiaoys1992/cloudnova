"""CLI: python -m app clean | ask "<question>" | demo.

- clean: delegates to the pipeline (python -m src.pipeline), owned by Session A.
- ask:   NL question -> prints answer + SQL.
- demo:  cleans if data is missing, then runs a few sample questions.
"""
from __future__ import annotations

import subprocess
import sys

from dotenv import load_dotenv

from src.agent import AgentError, ConfigError, DataError, ask
from src.agent.config import load_config

DEMO_QUESTIONS = [
    "What was our total recognized revenue in USD for paid invoices in 2024?",
    "How much have we given back in refunds?",
    "What is the churn rate for Enterprise accounts versus Starter accounts?",
]


def _print_answer(question: str, result: dict) -> None:
    print(f"Q: {question}\n")
    print(result["answer"])
    print("\nSQL:")
    print(result["sql"] or "(none)")


def cmd_clean() -> int:
    proc = subprocess.run([sys.executable, "-m", "src.pipeline"])
    return proc.returncode


def cmd_ask(question: str) -> int:
    try:
        result = ask(question)
    except (ConfigError, DataError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except AgentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _print_answer(question, result)
    return 0


def cmd_demo() -> int:
    cfg = load_config()
    if not (cfg.parquet_path.exists() and cfg.schema_path.exists()):
        print("Cleaned data not found; running `clean` first...\n")
        rc = cmd_clean()
        if rc != 0:
            print("ERROR: clean step failed; cannot run demo.", file=sys.stderr)
            return rc
        print()
    for i, q in enumerate(DEMO_QUESTIONS):
        try:
            result = ask(q)
        except (ConfigError, DataError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        _print_answer(q, result)
        if result["rows"]:
            print(f"rows: {result['rows'][:5]}")
        if i < len(DEMO_QUESTIONS) - 1:
            print("\n" + "-" * 60 + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print('Usage: python -m app clean | ask "<question>" | demo',
              file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "clean":
        return cmd_clean()
    if cmd == "ask":
        if not rest:
            print('Usage: python -m app ask "<question>"', file=sys.stderr)
            return 2
        return cmd_ask(" ".join(rest))
    if cmd == "demo":
        return cmd_demo()
    print(f"Unknown command '{cmd}'. Use clean | ask | demo.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
