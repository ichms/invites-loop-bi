# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`invites-loop-bi` is an OLAP **ELT pipeline** that extracts data from multiple operational
PostgreSQL source systems into a staging/data-warehouse layer, then transforms it for BI.
It runs as **Apache Airflow** DAGs (the `dags/` folder is the Airflow DAGs directory).
Python >= 3.13, managed with **uv**, `src/` layout.

> **State of the repo:** extract and load are implemented, tested against the real databases,
> and wired into DAGs. **`src/invites_loop_bi/transform/runner.py` is still empty** — that is the
> next stage. `main.py` and `src/pipeline.py` are leftover empty stubs; the real entry point is
> `src/invites_loop_bi/pipeline.py`.

## Commands

```bash
uv sync                                  # install deps (creates .venv); --inexact to keep undeclared packages
uv add <package>                         # runtime dep; uv add --dev <package> for tooling
source setup_env.sh                      # export AIRFLOW_CONN_* for local dev (see Connections)

uv run pytest                            # full suite (needs DB access)
INVITES_LOOP_BI_TEST_OFFLINE=1 uv run pytest   # skip every test that needs a database
uv run python tests/run_tests.py         # same suite without pytest; -k FILTER, --offline, -v

uv run python -m invites_loop_bi.pipeline iccoli --dry-run          # print the SQL, touch nothing
uv run python -m invites_loop_bi.pipeline iccoli --table tb_user_info
uv run python -m invites_loop_bi.pipeline discovery --overlap-minutes 5
```

No linter or CI is configured yet.

## Architecture

Extract → Load → Transform, one stage per subpackage under `src/invites_loop_bi/`.

**Rows never become Python objects.** A run streams `COPY (SELECT ...) TO STDOUT (FORMAT csv)`
from the source into a spooled buffer, and the loader streams that buffer into the warehouse with
`COPY ... FROM STDIN`. Values keep PostgreSQL's own text representation end to end, so `jsonb`,
arrays, enums, `numeric` and `interval` all survive exactly, and the copy is far faster than
row-wise inserts. There is no dataframe library on this path — do not reintroduce one without
re-reading `extract/introspect.py`, which explains why (a dataframe Struct unions the keys of
every row in a batch, silently corrupting `jsonb`).

- **`extract/`**
  - `extractor.py` — `IncrementalExtractor` and `FullRefreshExtractor`. The **first** run for a
    table has no watermark, so it reads the whole table with *no predicate at all* (rows whose
    watermark is NULL come along too). Later runs read only `watermark_expr > last_watermark`.
    `extract()` returns an `ExtractionResult` holding a rewound CSV buffer.
  - `introspect.py` — reads columns and the primary key from the source catalog, so staging DDL is
    never maintained by hand. Types are copied verbatim except those the warehouse lacks (enums,
    domains, composites, extension types), which become `text`.
  - `watermark.py` — `WatermarkManager` reads/upserts `stg_meta.watermarks`, keyed by
    `(source_system, schema_name, table_name)`, creating the schema/table on init (pass
    `ensure_table=False` for read-only callers such as a dry run).
- **`load/`** — `staging_loader.py` creates the staging table from the source catalog, copies the
  CSV into a temp table, then merges. See **Load strategies** below.
- **`transform/`** — `runner.py` runs SQL/transform steps over staging (**currently empty**).
- **`config/`** — `settings.py` holds connection ids and the staging layout; `__init__.py` is the
  target registry (`get_extraction_targets`); the `*_targets.py` files are the **declarative list
  of tables to extract** per source system.
- **`pipeline.py`** — `run_table()` (extract → load → commit for one table) and
  `run_source_system()`. Also a CLI, see Commands.
- **`connections.py`** — opens psycopg2 connections from `AIRFLOW_CONN_*`, falling back to
  `PostgresHook`. Autocommit is always **off**: the loader needs one transaction.

DB access uses raw connection/cursor objects (psycopg2-style: `conn.cursor()`, `%s` params,
`conn.commit()`).

### Ordering guarantee

`extract() → load() → commit()`, in that order, is the core invariant. The watermark moves **only
after** the rows are committed to staging, and a failure calls `mark_failed()`, which records the
error *without* moving the watermark. The next run therefore replays the same window rather than
skipping it. Loads are idempotent, so replaying is free.

The new watermark is the **highest watermark value among the rows actually loaded** (read from the
temp table), never a clock reading — that removes any gap between the query and the clock. The one
exception: a first run that finds nothing to anchor on falls back to the source clock, otherwise
the table would full-load forever.

### Load strategies

| Source table | Strategy |
|---|---|
| has a primary key | `INSERT ... ON CONFLICT (pk) DO UPDATE` — re-delivered rows overwrite |
| `*_FULL_REFRESH_TARGETS` | `TRUNCATE` then insert, in one transaction |
| **no** primary key (14 tables) | `DELETE` the extracted watermark window, then insert |

The third case exists because 14 incremental targets (2 sibc, 12 discovery lifelog tables) have no
primary key upstream — deliberately, since the keys were skipped for convenience and their absence
does not affect the analysis. Deleting exactly the window that is about to be inserted (reusing the
extractor's own predicate and bounds, `ExtractionPlan.predicate`) keeps them idempotent anyway.
They are listed in `KNOWN_MISSING_PRIMARY_KEY` in `tests/extract/test_introspect.py`, and the test
fails both when a new one appears and when one gains a key.

Every staging table gets a `_loaded_at timestamptz` bookkeeping column. Columns added upstream are
`ALTER TABLE ... ADD COLUMN`ed automatically; dropped or retyped columns are only logged.

### Extraction targets (config-driven)

Each source system has a `config/<system>_targets.py` exporting a list of dicts. Adding a table to
a pipeline means adding an entry here, not writing code. Systems: `iccoli`, `sibc`, `ichms`, `irs`,
`discovery` — 108 tables in total.

```python
{
    "schema_name": "public",
    "table_name": "tb_user_info",
    "watermark_col": "update_datetime",         # column used for incremental cutoff
    "fallback_watermark_col": "create_datetime" # used when watermark_col is null; None if none
}
```

The fallback exists because iccoli leaves `update_datetime` NULL until a row is actually updated;
the predicate then runs on `COALESCE(update_datetime, create_datetime)`. Most systems set it to
`None`. Alongside each list, `*_FULL_REFRESH_TARGETS` declares reference/meta tables with
`"load_type": "full_refresh"`.

`get_extraction_targets(system)` normalises entries to a fixed shape, validates them, and collapses
duplicate `(schema, table)` declarations (first wins, with a warning).

### Connections

All three databases live on one PostgreSQL server but are separate databases, so each hop needs its
own connection:

| Source system | Database | Airflow connection id |
|---|---|---|
| `iccoli` | `iccoli` (schema `public`) | `iccoli_db_conn` |
| `ichms`, `sibc`, `irs`, `discovery` | `invites_loop` (one schema each) | `invites_loop_db_conn` |
| warehouse | `invites_dw` (`stg_<system>`, `stg_meta`) | `olap_db_conn` |

Provided as `AIRFLOW_CONN_*` env vars (`AIRFLOW_CONN_ICCOLI_DB_CONN`, etc.); `setup_env.sh` sets
them for local development. The value is passed straight to libpq, so a `service=` string works as
well as a URI. Source connections are opened read-only.

Both sessions are expected to share a timezone — most columns are `timestamp with time zone` and
carry their offset through COPY, but a few (e.g. `tb_activity_user_log`) are naive `timestamp`, and
their watermarks only round-trip exactly while the sessions agree. `check_timezone_alignment()`
warns on a mismatch.

### PII handling

`src/utils/crypto.py` `generate_user_key(uuid, secret_salt)` produces a deterministic HMAC-SHA256
hex digest — used to pseudonymize user identifiers consistently across tables so they can still be
joined without exposing the raw UUID.

**It is not applied anywhere yet.** Because COPY never materialises values in Python, this cannot
run in flight; it belongs in the transform layer (pgcrypto's `hmac()` in SQL, or a post-load
update). Until then raw user UUIDs land in staging as-is.

## Testing

`tests/` mirrors the package. Tests take **no fixtures** and reach the database through a context
manager (`tests.db.sessions`), so the same functions run under pytest and under
`tests/run_tests.py`. Every warehouse session swallows the pipeline's `commit()` calls and rolls
back at the end, so the round-trip tests exercise real DDL/COPY/merge against real data **without
leaving anything behind** — keep it that way when adding tests.

## Repo notes / gotchas

- Source files use **tab indentation**; match that when editing existing files.
- Identifiers from config are interpolated into SQL, so they go through `quote_ident()`, which
  validates before quoting. Values are always `%s` parameters — except `COPY`, which takes no
  parameters, so watermark bounds are bound with `cursor.mogrify()`.
- `apache-airflow` is pinned to `~=3.2.2` in the dev group to match what is installed locally;
  bump it together with the deployed image. Airflow lives in `[dependency-groups] dev` because it
  is the runtime environment, not a library this package imports.
- Airflow 3.x: import from `airflow.sdk` (`from airflow.sdk import dag, task`), not
  `airflow.decorators`, which is deprecated.
- `polars`, `pandas` and `pyarrow` may still be installed in `.venv` but are no longer used or
  declared; a plain `uv sync` will prune them.
