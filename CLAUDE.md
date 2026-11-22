Project: CloudNova — spec-driven data pipeline + NL query agent (Track B)
Source of truth
Specs in /specs drive all code. Write the spec first, commit it, THEN generate code from it.
If a spec is ambiguous, pick the most defensible option, mark it `ASSUMPTION:` in the spec, and move on.
Context docs: docs/BUSINESS_CONTEXT.md (column meanings, known data issues, business rules,
stakeholder questions), docs/TASK.md (assignment + rubric), docs/data_profile.md (generated).
Two sessions work in this repo at the same time (no worktrees)
Each session edits ONLY the paths it owns.
Session	Owns
A (data)	scripts/, docs/data_profile.md, specs/cleaning_spec.md, specs/eval_spec.md, src/pipeline/, evals/, `pipeline:` section of config.yaml
B (agent)	specs/metrics_spec.md, specs/query_agent_spec.md, src/agent/, app/, tests/, `agent:` section of config.yaml
Shared, edit only when told: README.md, docs/architecture.md, docs/decisions.md, requirements.txt.
Contracts (the ONLY interface between A and B)
Pipeline writes to data/clean/:
`cleaned.parquet` — one cleaned table, queried by DuckDB as view `invoices`
`schema.json`:
    ```json
    {
      "table": "invoices",
      "row_count": 0,
      "columns": [
        {"name": "snake_case", "type": "VARCHAR|DOUBLE|BIGINT|DATE|BOOLEAN",
         "nullable": true, "description": "...", "allowed_values": null,
         "rules_applied": ["R01"]}
      ],
      "rules": [
        {"id": "R01", "description": "...", "action": "dropped|modified|flagged",
         "rows_affected": 0}
      ]
    }
    ```
`cleaning_report.md` — rows in/out, rows affected per rule.
Agent reads schema.json + specs/metrics_spec.md at runtime. Never hardcode column names in agent code.
Agent API: `ask(question: str) -> {"answer": str, "sql": str, "rows": list}`.
CLI: `python -m app clean | ask "<question>" | demo`. Evals: `python -m evals`.
Stack & conventions
Windows + PowerShell. Use PowerShell-compatible commands. Python venv at .venv.
Python 3.11+, pandas, DuckDB, anthropic SDK, PyYAML, python-dotenv.
Config in config.yaml; API key in .env (ANTHROPIC_API_KEY). No secrets or business constants in code.
Errors (missing API key, missing data, bad SQL) → one clear message, no raw stack trace.
Keep it simple. No features beyond the spec. Time budget is one hour total.
When the human overrides you, append a line to docs/decisions.md.
Git
Branch `dev`. Never commit to `main`.
Stage ONLY your own paths (`git add <paths>`). Never `git add .` or `git add -A`.
Commit after each completed step: `<area>: <what>`, e.g. `spec: cleaning rules`.
Before pushing: `git pull --rebase origin dev`, then `git push`.
Never commit .env.