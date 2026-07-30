# invites-loop-bi

A high-performance, config-driven ELT (Extract, Load, Transform) data pipeline designed to extract operational data from distributed microservices (`iccoli`, `ichms`, `sibc`, `irs`, `discovery`) and consolidate it into a central OLAP Data Warehouse.

---

## 📌 Overview

`invites-loop-bi` bridges the gap between transactional microservices and analytical reporting. By decoupling read-intensive analytical queries from production transactional DBs and API chains, this pipeline:
- **Eliminates API Chaining Latency**: Provides a centralized Read Model for complex cross-domain analytics.
- **Ensures Data Consistency**: Serves as the Single Source of Truth (SSOT) across all service domains.
- **Optimizes Performance**: Moves rows as `COPY ... CSV` bytes between PostgreSQL instances, never materializing them in Python.

**Status:** Extract and Load are implemented and tested against the real databases; **Transform is not built yet**. See [`todo.md`](todo.md) for the current plan and [`CLAUDE.md`](CLAUDE.md) for the architecture in depth.

---

## ✨ Key Features

- **Config-Driven Ingestion**: Adding a table means adding an entry to `config/<system>_targets.py` — no new Python. 107 tables across 5 source systems today.
- **Smart Watermark Tracking**: Incremental extraction with a fallback strategy (e.g. `COALESCE(update_datetime, create_datetime)` where `update_datetime` stays NULL until a row is edited). The first run for a table reads it whole; every run after reads only what changed.
- **Lossless Transfer**: `COPY (SELECT ...) TO STDOUT` piped into `COPY ... FROM STDIN` keeps PostgreSQL's own text representation end to end, so `jsonb`, arrays, enums, `uuid`, `numeric` and `interval` all arrive byte-identical — no type inference anywhere.
- **Schema Follows the Source**: Staging DDL, column types and primary keys are read from the source catalog. Columns added upstream are added automatically; types the warehouse lacks (enums, domains, composites) become `text`.
- **Three Idempotent Load Strategies**: upsert on the primary key, truncate-and-reload for reference tables, and delete-the-window-then-insert for sources with no key. Re-running any load is always safe.
- **Crash-Safe by Construction**: The watermark advances *only after* rows are committed to staging, so a failure replays the same window instead of skipping it.
- **Airflow 3 Ready**: One DAG per source system, one dynamically mapped task per table, with per-table retries and concurrency control.

---

## 📁 Project Structure

```text
invites-loop-bi/
├── dags/
│   └── elt_to_staging.py           # 5 DAGs, one mapped task per table
├── src/
│   ├── invites_loop_bi/
│   │   ├── config/                 # Declarative extraction targets
│   │   │   ├── __init__.py         # Target registry + validation
│   │   │   ├── settings.py         # Connection ids, staging layout
│   │   │   └── <system>_targets.py # Tables to extract, per source system
│   │   ├── extract/
│   │   │   ├── extractor.py        # COPY-based incremental / full-refresh extractors
│   │   │   ├── introspect.py       # Source catalog: columns, types, primary keys
│   │   │   └── watermark.py        # Watermark state in stg_meta.watermarks
│   │   ├── load/
│   │   │   └── staging_loader.py   # Temp table + COPY + merge, in one transaction
│   │   ├── transform/
│   │   │   └── runner.py           # (not implemented yet)
│   │   ├── connections.py          # AIRFLOW_CONN_* / PostgresHook → psycopg2
│   │   └── pipeline.py             # extract → load → commit; also a CLI
│   └── utils/
│       └── crypto.py               # Deterministic HMAC user-key pseudonymization
├── tests/                          # 110 tests; pytest or the standalone runner
├── setup_env.sh.example            # Connection env var template
├── pyproject.toml
├── CLAUDE.md                       # Architecture and conventions
└── todo.md                         # Progress and next steps
```

---

## 🛠️ Tech Stack & Prerequisites

- **Python**: 3.13+, managed with [uv](https://docs.astral.sh/uv/)
- **Data Movement**: PostgreSQL `COPY` via psycopg2 — no dataframe layer
- **Storage**: PostgreSQL / Azure PostgreSQL (source systems and OLAP DW)
- **Orchestration**: Apache Airflow 3.2+ (optional; the pipeline runs standalone too)

---

## 🚀 Getting Started

```bash
uv sync                                  # create .venv and install dependencies
cp setup_env.sh.example setup_env.sh     # fill in real credentials (gitignored)
source setup_env.sh                      # export AIRFLOW_CONN_*
```

Connections are Airflow connection ids resolved from `AIRFLOW_CONN_*`, falling back to `PostgresHook`. The value is passed straight to libpq, so a `service=` string works as well as a URI.

| Source system | Database | Connection id |
|---|---|---|
| `iccoli` | `iccoli` | `iccoli_db_conn` |
| `ichms`, `sibc`, `irs`, `discovery` | `invites_loop` | `invites_loop_db_conn` |
| warehouse | `invites_dw` | `olap_db_conn` |

### Running it

```bash
# Print the SQL each table would run, without touching anything
uv run python -m invites_loop_bi.pipeline iccoli --dry-run

# Load a single table, or a whole source system
uv run python -m invites_loop_bi.pipeline iccoli --table tb_user_info
uv run python -m invites_loop_bi.pipeline sibc
```

Data lands in `stg_<source_system>.<table>` in the warehouse, with a `_loaded_at` column; extraction state lives in `stg_meta.watermarks`.

### Tests

```bash
uv run pytest                                  # full suite (needs database access)
INVITES_LOOP_BI_TEST_OFFLINE=1 uv run pytest   # skip everything needing a database
uv run python tests/run_tests.py               # same suite without pytest installed
```

Round-trip tests exercise real DDL, `COPY` and merges against the real databases inside a transaction that is **rolled back**, so they leave the warehouse untouched.

---

## ⚙️ Adding a Table

Add an entry to the relevant `config/<system>_targets.py` — nothing else:

```python
{
    "schema_name": "public",
    "table_name": "tb_user_info",
    "watermark_col": "update_datetime",          # incremental cutoff
    "fallback_watermark_col": "create_datetime", # used where watermark_col is NULL
}
```

Reference tables go in the matching `*_FULL_REFRESH_TARGETS` list with `"load_type": "full_refresh"`. Oversized payload columns can be skipped with `"exclude_columns": ("meal_data",)`.
