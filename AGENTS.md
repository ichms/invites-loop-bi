# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`invites-loop-bi` is an OLAP **ELT pipeline** that extracts data from multiple operational
PostgreSQL source systems into a staging/data-warehouse layer, then transforms it for BI.
It runs as **Apache Airflow** DAGs (the `dags/` folder is the Airflow DAGs directory).
Python >= 3.13, managed with **uv**, `src/` layout.

> **State of the repo:** extract, load and transform are all implemented and tested against
> the real databases. The transform layer is **dbt** (`dbt/` at the repo root): sources over
> all five landing schemas, staging views, allow-list seed + drift test, and the full star —
> six dims and twelve facts (`fct_user_day`, `fct_user_disease_day`, `fct_measurement`,
> `fct_wearable_day`, six source-grain `fct_wearable_*` observation facts,
> `fct_coaching_event`, `fct_app_action`) with grain and FK tests. `dbt build` is 388/388
> green; `pytest` 125/125. **`fct_user_day` is a dense behavioural panel** since 2026-08-07
> (every user-day from the earlier of enrolment and first activity, ~76k rows) — the zero
> days are the denominator, and a reconciliation test asserts no activity falls outside the
> spine. Read `todo.md` "The frames we now work under" before changing it. **Wearable counts
> are not constants** (2026-08-10): those streams watermark on measurement time and the
> source backfills for ~30 days, so the count at a fixed cutoff rises with extraction date —
> quote one only with its extraction date. All five wearable streams carry a 30-day `lookback_days`
> (heart rate included since 2026-08-13 for `fct_wearable_day` intensity); see A′ in `todo.md`. DAGs are
> **written but have never run on a schedule** — five ELT
> DAGs declare 01:00 KST and `transform_dbt_build` 02:00 KST, but no scheduler is deployed,
> all five ELT DAGs are paused, and `transform_dbt_build` has never been parsed. Every load
> and `dbt build` to date was a manual CLI run; "who runs the scheduler" is Q-13, still open.
> Metric views (`v_pi_*` / `v_bridge_*`) sit in
> `dbt/models/marts/metrics/`. **All five phases are complete**; Superset runs locally from
> `deploy/superset/` (pinned compose stack, `superset_reader` role, dataset registration and
> the PI dashboard as code, Korean metrics guide). The remaining open item is **Q-04, a named
> owner in writing** — see `HANDOVER.md`. Modelling decisions live in
> `INVITES_LOOP_BI_DECISION_LOG.md` and `IMPLEMENTATION_PLAN.md` (which records where
> measurement overrode the log — §3), and the Q-11 column classification in `PII_INVENTORY.md`
> — read them before touching `dbt/`. Generate dbt documentation with
> `dbt docs generate --project-dir dbt --static` (open `dbt/target/static_index.html`); `HOWTO.md` covers extending the marts, exposing
> models to Superset, and MCP restriction. `main.py` and `src/pipeline.py` are leftover empty stubs; the real
> entry point is `src/invites_loop_bi/pipeline.py`.

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

uv run dbt build --project-dir dbt       # transform layer (models + tests); needs setup_env.sh
uv run dbt debug --project-dir dbt       # check the dbt <-> warehouse connection
uv run dbt docs generate --project-dir dbt --static  # lineage HTML → dbt/target/static_index.html
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
- **`transform/`** — a pointer only: the T is **dbt**, in `dbt/` at the repo root. dbt treats the
  `stg_<system>` landing schemas as sources and writes to two schemas of its own: `staging`
  (views: dedupe, casts, `user_no`→`user_id` translation, allow-listed JSONB flattening) and
  `marts` (dims/facts/metric views — the only schema the BI read-only role sees). Credentials
  come from `DBT_PG_*` env vars (`setup_env.sh`); marts materialise as `table`, deliberately —
  no incremental models until a build exceeds ~15 minutes.
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
`discovery` — 123 tables in total.

```python
{
    "schema_name": "public",
    "table_name": "tb_user_info",
    "watermark_col": "update_datetime",          # column used for incremental cutoff
    "fallback_watermark_col": "create_datetime", # used when watermark_col is null; None if none
    "exclude_columns": ("ci", "di"),             # optional: never read, staged or stored
    "row_filter": LOOP_USERS_ONLY,               # optional: SQL predicate run in the source DB
}
```

The fallback exists because iccoli leaves `update_datetime` NULL until a row is actually updated;
the predicate then runs on `COALESCE(update_datetime, create_datetime)`. Most systems set it to
`None`. Alongside each list, `*_FULL_REFRESH_TARGETS` declares reference/meta tables with
`"load_type": "full_refresh"`.

`exclude_columns` exists for huge payloads *and* for data minimisation (identity columns).
`row_filter` restricts every user-keyed iccoli table to Loop-cohort accounts (`LOOP_USERS_ONLY`,
a subquery on `tb_ext_user_mapper`); community app users never leave the source system. It is
self-contained SQL (no `%s`, literal `%` doubled — it goes through `mogrify()`) and it is kept
out of `ExtractionPlan.predicate`, which the loader replays against *staging* for keyless-table
deletes. Caveat: a user who enrols later gains rows only from the current watermark onwards —
after an enrolment wave, delete the iccoli rows from `stg_meta.watermarks` to force a full,
idempotent re-read (see the comment in `iccoli_targets.py`).

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

Since 2026-08-06, minimisation also happens at the **EL boundary** (IMPLEMENTATION_PLAN.md N-01/
N-02): direct identifiers (CI/DI, names, phone, email, push/device tokens) are `exclude_columns`,
`tb_ext_user_preinfo` is not a target, and user-keyed iccoli tables carry the cohort `row_filter`.
`scripts/20260806_pii_cleanup.sql` retro-applied the policy to already-landed data. If a model
needs a field that is excluded here, that is a policy conversation, not a config edit.

### Site affiliation is multi-valued — the Jeju problem

> **Updated 2026-08-12 after the Jeju launch** — read the dated update at the
> end of this section first. Several measurements below are superseded, and the
> section's headline claim turned out to be only half-true.

**The business need:** "this person was in Ulsan and is now *also* in Jeju." One
person, two affiliations. Raised by the owner 2026-08-10 as "there is only one
field but two values".

**That premise is true of our warehouse and false of the source.** Measured
2026-08-10 (read-only; both tables are already landed, so closing this needs no
extraction):

- **`ichms.auth_user_customer` is already a temporal bridge.** Surrogate PK
  `user_customer_id`, **no unique constraint on `user_id`**, plus `linked_dt`
  and a nullable `unlinked_dt`. Many rows per user is not an edge case — 503 of
  581 users already carry more than one link, 501 of them simultaneously active.
  The source can express Ulsan-and-Jeju today, unchanged.
- **At that time, `dim_user.site_id` was a hardcoded string literal**,
  `'KR_LOOP_PILOT'`, on every row. It had no source at all. Superseded by the
  2026-08-13 current-site update below.
- `dim_deployment_site`'s header claims Jeju "arrive[s] as rows here and as a
  populated `dim_user.site_id` — no restructuring." **That claim is wrong.** A
  scalar `site_id` cannot hold two values, and `dim_user` is SCD Type 1 (D-08),
  so writing Jeju over Ulsan would silently re-attribute every historical fact
  for that user. Correct the header when this is fixed.

State measured 2026-08-10: all 404 `dim_user` users join cleanly to `auth_user_customer`,
and **all 404 resolve to ULSAN**. JEJU exists as a customer with 14 linked users,
**none of them in `dim_user`** — the cohort is the 404 sibc users, so Jeju
arriving for real also reopens the population question.

**The shape of the fix:** a bridge mart at
`(user_id, site_id, valid_from, valid_to)` sourced from `auth_user_customer`,
with `dim_user` keeping one row per user and *losing* its literal `site_id`
(or keeping it only as an explicitly-defined primary/reporting site). Do not put
site on `fct_user_day`'s grain — it is user × day, and user × day × site
double-counts every metric for a dual-affiliated user.

**Four things that bite, and are not solved by the bridge:**

1. **RESOLVED 2026-08-13: `auth_customer` conflates regions with application tenants.** Its seven rows
   are 울산 and 제주 *and* LIS, 아이콜리, iCHMS Operator/Expert/Customer Web. Built
   naively, `dim_deployment_site` would list "LIS" as a deployment site. The
   owner-approved allow-list is Ulsan `2e0a3387-7058-4f9e-a134-2017f7b7000b`
   and Jeju `778d4ff7-ab76-4070-a9a9-716fac93d9c9`, and no other customer.
2. **The data cannot currently distinguish "moved" from "both".** Only 10 of
   1,113 link rows have `unlinked_dt` set, so a relocation and a dual affiliation
   both appear as two open links. No modelling fixes that — it is a process gap
   upstream, and it decides whether overlapping active links are legal.
3. **Denominators stop being disjoint.** Once anyone is in both, "Ulsan users +
   Jeju users" double-counts people. Same failure class as the §5.2 denominator
   artifact in `todo.md` Frame 3.
4. **A GUI filter cannot traverse a temporal bridge.** Superset datasets are
   single relations; a chart filter on site needs a view — registered as a
   dataset — that resolves the as-of rule, or non-SQL users get wrong answers
   with no indication anything happened.

#### Update 2026-08-12 — Jeju is live, and the premise above is only half-true

Jeju operations started 2026-08-10. A patient-registration error that day was
resolved by a developer manually re-pointing internal staff accounts from Ulsan
to Jeju **with direct DML in production**. Diffing the source against the
warehouse's 2026-08-05 snapshot (the last ichms load before the freeze;
freeze lifted 2026-08-13) established the following.

- **13 rows of `auth_user_customer` were UPDATEd in place** — `customer_id`
  flipped ULSAN→JEJU on the existing row, `linked_dt`/`unlinked_dt` untouched.
  35 rows are new (Jeju registrations plus tenant pairs), none deleted. All 13
  re-pointed users are in `dim_user`. This resolves the "Minor" anomaly that
  used to close this section: JEJU links whose `linked_dt` (2025-11-27) predates
  JEJU's own `created_dt` (2026-06-22) are re-pointed Ulsan-era rows. The 8/5
  snapshot holds zero JEJU rows, so this was the first such flip. The 13 PKs
  are recoverable any time by re-running the same diff.
- **The actual switch time (~13:07 KST, 8/10) exists nowhere in the database.**
  The table has no `updated_dt` and the change bypassed the application; the
  time is known only from the dev team's message. `linked_dt` on those 13 rows
  now lies about affiliation start.
- **The application (1.3) enforces user:customer 1:1 at code level.** Staff
  hold exactly one of ULSAN/JEJU at a time; testing the other site means
  flipping, and each flip is a manual request to a developer — no admin path
  exists ("변경요청하셔야 합니다"). So the *schema* is a temporal bridge but
  the *write path* treats it as a scalar, and the history table accumulates
  non-history. The headline above — "the constraint is ours, not the
  source's" — is therefore only half-true: ours is the only stored single
  value, but the source's single value lives in the app and its write
  discipline. Storage capability is not data trustworthiness.
- The 1:1 constraint does **not** force destructive writes: unlinking the old
  row and inserting a new one keeps exactly one active zone and satisfies the
  app unchanged. The in-place UPDATE was convenience, not necessity.
- **Incremental extraction can never see these flips.** The table used to
  watermark on `linked_dt` alone, which an in-place UPDATE does not touch.
  Converted to a full-refresh target on 2026-08-13 (small, has a PK). A dbt
  snapshot over the staging table is the only warehouse-side way to catch
  *future* flips at load-cadence resolution if full-refresh is ever dropped.
- **Staff cannot be inferred from the data.** Two further staff accounts (new
  hires, confirmed by the owner 2026-08-12) have no Ulsan history at all — JEJU
  from their first link. At least 15 staff accounts are known, 14 of them
  inside the analysis cohort; no source system carries a staff flag. The roster
  must be owner-provided (a seed), never derived from re-point traces.
- **The cohort grew during the 2026-08-10–13 freeze**: sibc `user_master`
  404→412, iccoli mapper 441→450 (measured 2026-08-12). Resume deletes the
  iccoli watermark rows to force a full, idempotent re-read.
#### Update 2026-08-13 — current-site reporting enabled

The owner supplied the two deployment-site UUIDs above and chose current-site
mapping for `dim_user`. `dim_deployment_site` now has Ulsan and Jeju from
`auth_customer`; `dim_user.site_id` reads the one active approved
`auth_user_customer` link. At the 2026-08-13 extraction all 416 cohort users
have exactly one: 392 Ulsan and 24 Jeju. This is an SCD1 **current-value filter**,
not history. The 13 in-place flips still erase their previous site and switch
time, so never use `dim_user.site_id` to attribute a past event as-of its date.

Still blocked on the dev team: unlink+insert discipline for manual flips,
notification of manual production DML, the app read rule if multiple approved
links become active, and whether the 13 flipped rows will be repaired. A
temporal site bridge, historical/as-of site metrics and simultaneous
Ulsan-and-Jeju semantics remain out of scope until those contracts exist.

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
