# CloudNova — System Architecture (Track B)

Data flows one way: a dirty CSV is cleaned by a spec-driven pipeline into a single
Parquet table plus a `schema.json` contract; the NL query agent reads that contract
at runtime, turns a question into guarded DuckDB SQL, and returns an answer with the
SQL shown. An independent oracle re-derives the expected metrics for the eval harness.

```mermaid
flowchart TD
    CSV[("data/raw/cloudnova_invoices.csv<br/>~5k dirty rows")]

    subgraph pipe["src/pipeline — Session A"]
        CLEAN["clean.py — rules R01..R17<br/>dedup, normalize categories/dates,<br/>FX to USD, derive mrr_usd"]
    end

    subgraph clean["data/clean — the only contract"]
        PARQ[("cleaned.parquet<br/>view: invoices")]
        SCHEMA[["schema.json<br/>columns, types, allowed_values, rules"]]
        REPORT["cleaning_report.md<br/>rows in/out, per-rule counts"]
    end

    DUCK{{"DuckDB — register parquet as view invoices"}}

    MSPEC["specs/metrics_spec.md"]
    FEWSHOT["src/agent/few_shots.yaml"]

    subgraph agent["src/agent — Session B"]
        PROMPT["prompt assembly<br/>schema.json + metrics_spec + few_shots"]
        SQLGEN["NL to SQL — LLM call"]
        GUARD["guardrails<br/>SELECT/WITH only, row cap, timeout"]
        EXEC["execute query<br/>retry once on SQL error"]
        ANSWER["answer — 2nd LLM call<br/>one paragraph quoting the numbers"]
    end

    CLI["app CLI<br/>python -m app clean | ask | demo"]

    subgraph eval["evals"]
        ORACLE["oracle.py<br/>independent pandas, no src imports"]
        HARNESS["harness — python -m evals<br/>compare vs tolerance"]
        RESULT{"PASS / FAIL / XFAIL"}
    end

    CSV --> CLEAN
    CLEAN --> PARQ
    CLEAN --> SCHEMA
    CLEAN --> REPORT

    PARQ --> DUCK
    SCHEMA --> PROMPT
    MSPEC --> PROMPT
    FEWSHOT --> PROMPT
    PROMPT --> SQLGEN --> GUARD --> EXEC --> ANSWER
    GUARD -. "reject: not read-only" .-> ANSWER
    DUCK --> EXEC

    CLI -- "clean" --> CLEAN
    CLI -- "ask / demo -> agent.ask()" --> PROMPT
    ANSWER --> CLI

    PARQ --> ORACLE
    ORACLE --> HARNESS
    HARNESS -- "agent.ask() per case" --> PROMPT
    ANSWER --> HARNESS
    HARNESS --> RESULT
```

## How to read it

- **Contract boundary.** `data/clean/` is the *only* interface between the two halves.
  The pipeline writes `cleaned.parquet` + `schema.json` + `cleaning_report.md`; the
  agent reads `schema.json` at runtime and never hardcodes column names.
- **Agent path.** `schema.json` + `specs/metrics_spec.md` + `src/agent/few_shots.yaml`
  are assembled into the prompt → the LLM emits one SQL statement → guardrails reject
  anything that is not a single read-only `SELECT`/`WITH` → the query runs against the
  DuckDB `invoices` view under a row cap and timeout (one retry if it errors) → a
  second short LLM call turns the rows into a plain-English answer. `ask()` returns
  `{answer, sql, rows}`.
- **Entry point.** `python -m app` exposes `clean` (delegates to `python -m src.pipeline`),
  `ask "<q>"`, and `demo`.
- **Evaluation.** `evals/oracle.py` computes expected values independently (plain pandas
  over the Parquet, no `src/` imports) and the harness compares the agent's answer per
  case within tolerance — `PASS` / `FAIL` / `XFAIL` (one case, E05, is an expected fail).
