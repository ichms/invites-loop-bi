# invites-loop-bi

A config-driven **ELT** pipeline that extracts operational data from five PostgreSQL source systems (`iccoli`, `ichms`, `sibc`, `irs`, `discovery`), lands it in a warehouse, and transforms it with **dbt** into a star schema, metric views, and an **analysis-ready behavioural panel**.

---

## 📌 Overview

`invites-loop-bi` bridges transactional microservices and analytical reporting. By decoupling read-intensive analytical queries from production transactional DBs and API chains, this pipeline:

- **Eliminates API chaining latency**: a centralized read model for cross-domain analytics.
- **Ensures consistency**: one place where a metric is defined, in git, reviewable.
- **Optimizes performance**: moves rows as `COPY ... CSV` bytes between PostgreSQL instances, never materializing them in Python.

**Status:** all five phases are complete. `dbt build` **211/211**, `pytest` **117/117**. Extract → load → transform → marts → metric views → Metabase all work — **when invoked by hand**. Nothing runs unattended yet; no Airflow scheduler is deployed (see [`todo.md`](todo.md) §3).

Architecture in depth: [`CLAUDE.md`](CLAUDE.md). Decisions and rejected options: [`INVITES_LOOP_BI_DECISION_LOG.md`](INVITES_LOOP_BI_DECISION_LOG.md). Where measurement overruled the plan: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §3. Operational recipes: [`HOWTO.md`](HOWTO.md).

---

## 🧭 The two audiences, and why that shapes the schema

This warehouse serves two populations with genuinely different needs, and conflating them produces a system that satisfies neither.

**The Planning Team** author questions in a GUI and must never write SQL (D-17). They are served by the star schema: conformed dimensions, facts with a declared grain, and FK metadata pushed into Metabase so cross-table filtering works without SQL.

**Analysts and data engineers** ask questions no GUI can answer — rank correlation, Mann-Whitney U, OLS with covariate control. **No BI tool does this**, so the requirement lands on the warehouse rather than on the viewer: the marts must be shaped so a notebook can pick them up directly.

That second requirement is why `fct_user_day` is a **dense** panel. See [Analysis-ready marts](#-analysis-ready-marts).

---

## ✨ Key Features

- **Config-driven ingestion**: adding a table means adding an entry to `config/<system>_targets.py` — no new Python. **123 tables** across 5 source systems today.
- **Smart watermark tracking**: incremental extraction with a fallback (`COALESCE(update_datetime, create_datetime)` where `update_datetime` stays NULL until a row is edited). The first run reads the table whole; every run after reads only what changed.
- **Lossless transfer**: `COPY (SELECT ...) TO STDOUT` piped into `COPY ... FROM STDIN` keeps PostgreSQL's own text representation end to end, so `jsonb`, arrays, enums, `uuid`, `numeric` and `interval` arrive byte-identical — no type inference anywhere.
- **Schema follows the source**: staging DDL, column types and primary keys are read from the source catalog. Columns added upstream are added automatically; types the warehouse lacks become `text`.
- **Three idempotent load strategies**: upsert on the primary key, truncate-and-reload for reference tables, and delete-the-window-then-insert for keyless sources. Re-running any load is safe.
- **Crash-safe by construction**: the watermark advances *only after* rows are committed to staging, so a failure replays the same window instead of skipping it.
- **Data minimisation at the EL boundary**: direct identifiers are never extracted, and user-keyed `iccoli` tables carry a cohort row filter, so non-cohort users never leave the source system.
- **dbt transform layer**: staging views, six dimensions, five facts with grain and FK tests, and metric views — all tested on every build.

---

## 📁 Project Structure

```text
invites-loop-bi/
├── dags/
│   ├── elt_to_staging.py           # 5 DAGs, one mapped task per table
│   └── transform_dbt_build.py      # source freshness + dbt build
├── dbt/                            # the T: staging views → marts → metric views
│   ├── models/
│   │   ├── staging/                # dedupe, casts, user_no→user_id, JSONB allow-list
│   │   └── marts/
│   │       ├── dim_*.sql fct_*.sql # 6 dims, 5 facts, grain + FK tests
│   │       └── metrics/            # v_pi_* / v_bridge_* — the quotable numbers
│   ├── tests/                      # singular tests, incl. spine reconciliation
│   └── docs/dbt_docs.html          # committed lineage + column docs (Q-07)
├── analysis/                       # one-off notebooks (scipy / statsmodels)
├── src/
│   ├── invites_loop_bi/
│   │   ├── config/                 # declarative extraction targets per system
│   │   ├── extract/                # COPY extractors, catalog introspection, watermarks
│   │   ├── load/                   # temp table + COPY + merge, in one transaction
│   │   ├── connections.py          # AIRFLOW_CONN_* / PostgresHook → psycopg2
│   │   └── pipeline.py             # extract → load → commit; also a CLI
│   └── utils/crypto.py             # HMAC user-key helper — currently UNUSED, see todo.md
├── tests/                          # 117 tests; pytest or the standalone runner
├── CLAUDE.md · HOWTO.md · todo.md
└── INVITES_LOOP_BI_DECISION_LOG.md · IMPLEMENTATION_PLAN.md · PII_INVENTORY.md
```

---

## 🛠️ Tech Stack & Prerequisites

- **Python**: 3.13+, managed with [uv](https://docs.astral.sh/uv/)
- **Data movement**: PostgreSQL `COPY` via psycopg2 — no dataframe layer
- **Storage**: PostgreSQL / Azure PostgreSQL (source systems and OLAP DW)
- **Transform**: dbt Core 1.10 + dbt-postgres (Apache 2.0; D-03)
- **Viewer**: Metabase OSS, from the sibling repo `invites-loop-bi-deploy`
- **Orchestration**: Apache Airflow 3.2+ (the pipeline also runs standalone)

---

## 🚀 Getting Started

```bash
uv sync                                  # create .venv and install dependencies
cp setup_env.sh.example setup_env.sh     # fill in real credentials (gitignored)
source setup_env.sh                      # export AIRFLOW_CONN_* and DBT_PG_*
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

# Transform
uv run dbt build --project-dir dbt        # models + tests
uv run dbt debug --project-dir dbt        # check the warehouse connection
```

Data lands in `stg_<source_system>.<table>` with a `_loaded_at` column; extraction state lives in `stg_meta.watermarks`. dbt writes `staging` (views) and `marts` (tables) — `marts` is the only schema the BI read-only role can see.

### Tests

```bash
uv run pytest                                  # full suite (needs database access)
INVITES_LOOP_BI_TEST_OFFLINE=1 uv run pytest   # skip everything needing a database
uv run python tests/run_tests.py               # same suite without pytest installed
```

Round-trip tests exercise real DDL, `COPY` and merges against the real databases inside a transaction that is **rolled back**, so they leave the warehouse untouched.

---

## 📊 Analysis-ready marts

`fct_user_day` is a **dense** user × day panel: every day from the earlier of enrolment and first observed activity, up to the observation frontier — including days with no activity at all.

That density is the point. A behavioural rate needs the zero days, because **the zero days are the denominator**. Aggregating over a spine of only-active days divides by the wrong number and biases every rate upward. This is not theoretical: a published "dietary logging is weak" verdict turned out to be a pure denominator artifact — per-recorder intensity had *risen* from 6.2 to 21.1 days/month, not fallen.

What the panel carries, and why:

| Column group | Why it exists |
|---|---|
| `days_since_joined`, `months_since_joined` | Enrolment spans nine months, so calendar time mixes cohort entry with behaviour change. Trajectories are only comparable on relative time. Negative values are deliberate — they give a pre-period. |
| `app_login_events`, `did_login` | **The dominant control variable.** Routine completion runs ~24% at 0–5 monthly login days against ~65–72% at 16+, and conditioning on it can reverse the sign of other effects. Any comparison that ignores it is measuring app usage. |
| `routines_delivered` / `routines_completed` | A denominator pair. Never compute a rate without both in the same row. |
| `manual_measurements`, `meal_records` → `active_input_events` | Deliberate acts. |
| `wearable_streams_active`, `had_passive_collection` | Passive collection. Kept separate: a worn watch accumulates data on its own, so summing it with active input averages a behaviour with a device state. |

`dbt/tests/assert_user_day_spine_loses_no_activity.sql` asserts the fact's per-channel totals equal staging's. The spine is bounded, so any row outside those bounds would be dropped *silently* — that test is what makes the bounds safe to change.

---

## ⚙️ Adding a Table

Add an entry to the relevant `config/<system>_targets.py` — nothing else:

```python
{
    "schema_name": "public",
    "table_name": "tb_user_info",
    "watermark_col": "update_datetime",          # incremental cutoff
    "fallback_watermark_col": "create_datetime", # used where watermark_col is NULL
    "exclude_columns": ("ci", "di"),             # never read, staged, or stored
}
```

Reference tables go in the matching `*_FULL_REFRESH_TARGETS` list with `"load_type": "full_refresh"`.

`exclude_columns` serves data minimisation as well as payload size. If a model needs a field excluded there, that is a policy conversation (see `PII_INVENTORY.md`), not a config edit.

For adding a dim or fact, and for pushing FK metadata to Metabase, see [`HOWTO.md`](HOWTO.md) §2 and §3.
