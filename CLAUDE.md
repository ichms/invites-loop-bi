# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`invites-loop-bi` is an OLAP **ELT pipeline** that extracts data from multiple operational
PostgreSQL source systems into a staging/data-warehouse layer, then transforms it for BI.
It is designed to run as **Apache Airflow** DAGs (the `dags/` folder is the Airflow DAGs
directory). Python >= 3.13, managed with **uv**, `src/` layout.

> **State of the repo:** this is early scaffolding. Much of the skeleton exists but several
> core modules are currently **empty** — `src/pipeline.py`, `src/invites_loop_bi/config/settings.py`,
> `src/invites_loop_bi/load/staging_loader.py`, `src/invites_loop_bi/transform/runner.py`, and
> `dags/` has no DAG files yet. When implementing, wire these together per the architecture below.

## Commands

```bash
uv sync                       # install/lock dependencies (creates .venv)
uv add <package>              # add a runtime dependency (deps are managed via pyproject/uv, not pip)
uv run python -m <module>     # run a module inside the project venv
source setup_env.sh           # export Airflow connection env vars for local dev (see below)
```

There is **no test runner, linter, or CI configured yet** — `tests/` is empty and `pyproject.toml`
declares no dev tooling. `main.py` is a placeholder stub, not the pipeline entry point.

## Architecture

The pipeline follows Extract → Load → Transform, one stage per subpackage under
`src/invites_loop_bi/`:

- **`extract/`** — `BaseExtractor` (`extractor.py`) pulls rows from a source DB. Extraction is
  **watermark-based incremental**: on the first run for a table (no watermark) it does a full
  load; afterwards it selects only rows where `watermark_col` is between the last watermark and
  the current execution time. `WatermarkManager` (`watermark.py`) reads/upserts watermark
  timestamps in the metadata table `stg_meta.watermarks`, keyed by
  `(source_system, schema_name, table_name)`, and auto-creates that schema/table on init.
- **`load/`** — `staging_loader.py` loads extracted frames into the staging DB (currently empty).
- **`transform/`** — `runner.py` runs SQL/transform steps over staging (currently empty).
- **`config/`** — `settings.py` holds shared config (connections, etc.); the `*_targets.py`
  files are the **declarative list of tables to extract** per source system.

Data is handled with **polars** (`pl`). DB access uses raw connection/cursor objects
(psycopg-style: `conn.cursor()`, `%s` params, `conn.commit()`).

### Extraction targets (config-driven)

Each source system has a `config/<system>_targets.py` exporting a list of dicts. Adding a table
to a pipeline means adding an entry here, not writing code. Systems:
`iccoli`, `sibc`, `ichms`, `irs`, `discovery` (plus `invites_loop`).

Each entry shape:
```python
{
    "schema_name": "public",
    "table_name": "tb_user_info",
    "watermark_col": "update_datetime",        # column used for incremental cutoff
    "fallback_watermark_col": "create_datetime" # used when watermark_col is null; None if none
}
```
`discovery_targets.py` additionally defines `DISCOVERY_FULL_REFRESH_TARGETS` — reference/meta
tables with `"load_type": "full_refresh"` instead of a watermark (fully reloaded each run).

### Connections

Source and warehouse DBs are provided as **Airflow connections** via `AIRFLOW_CONN_*` env vars,
e.g. `AIRFLOW_CONN_ICCOLI_DB_CONN`, `AIRFLOW_CONN_INVITES_LOOP_DB_CONN`, `AIRFLOW_CONN_OLAP_DB_CONN`.
`setup_env.sh` sets these for local development. Extractors take a read-only **source connection**
and a read-write **meta/DW connection** separately.

### PII handling

`src/utils/crypto.py` `generate_user_key(uuid, secret_salt)` produces a deterministic
HMAC-SHA256 hex digest — used to pseudonymize user identifiers consistently across tables so
they can still be joined without exposing the raw UUID.

## Repo notes / gotchas

- **`iccoli_public.sql`** is a ~742KB `pg_dump` of the iccoli `public` schema — a source-schema
  reference, not something to run against production.
- Existing SQL in `extractor.py` uses f-string interpolation of values; prefer parameterized
  queries (`%s`) as done in `watermark.py` when extending it.
- There is a **typo** in `watermark.py`: `_ensure_watermark_table()` creates `stg_meta.watermakrs`
  while every query reads/writes `stg_meta.watermarks`. Fix the table name when touching this code.
- The repo has **no commits yet** — everything is untracked working tree.
- Source files use **tab indentation**; match that when editing existing files.
