# invites-loop-bi — progress and next steps

Last updated: 2026-07-30. Architecture lives in `CLAUDE.md`; this file is the working plan.

## Where we are

**Extract and Load are done, and the first production load ran on 2026-07-30: all 107 tables
across the 5 systems are in staging, every watermark row is SUCCESS.** Incremental runs from here
on only pick up changes. Because the warehouse is no longer empty, tests that assume first-run
state now call `tests.db.reset_staging()` inside their rolled-back transaction.

Transform is deliberately untouched: `src/invites_loop_bi/transform/runner.py` is still empty.

| Piece | State |
|---|---|
| `config/` — 107 targets across 5 systems, registry + validation | done |
| `extract/` — COPY-based extractor, catalog introspection, watermarks | done |
| `load/` — staging loader (auto-DDL, upsert / truncate / delete-window) | done |
| `pipeline.py` — `run_table`, `run_source_system`, CLI | done |
| `connections.py` — `AIRFLOW_CONN_*` → psycopg2, `PostgresHook` fallback | done |
| `dags/elt_to_staging.py` — 5 DAGs, one mapped task per table | done, never executed |
| `tests/` — 110 tests, both pytest and a standalone runner | done |
| `transform/runner.py` | **empty — next phase** |
| OLAP layer schema | **not started** |

### Is the plan (finish E+L → design the OLAP schema → build transform) sound?

Yes. Staging is a faithful mirror of the sources, so the transform layer can be designed and
rewritten freely without re-extracting anything. Nothing in the current code assumes a particular
warehouse model.

Three caveats, all about **what staging retains** — cheap to decide now, expensive later:

1. **Upsert overwrites history.** Staging keeps only the current version of a mutable row. Once
   `tb_user_info.status` changes and a load runs, the previous value is gone for good. Event-shaped
   sources (`tb_*_log`, `*_hist`, lifelog tables) are append-only and keep their own history, so
   this only bites the dimension tables. If the OLAP layer needs point-in-time answers ("what was
   this user's status in March"), that has to be designed **before** the first production load.
2. **Hard deletes never arrive.** Watermark extraction cannot see a deleted row, so staging keeps
   rows that no longer exist upstream. iccoli soft-deletes (`purged_datetime`,
   `deactivated_datetime`) so it is fine; other systems need checking. Also relevant to deletion
   requests — a user purged upstream would linger in staging.
3. **PII lands raw in staging — decided: de-identify in the transform phase.**
   `utils/crypto.py:generate_user_key()` cannot run in flight because COPY never materialises
   values in Python, so pseudonymization becomes a transform step (pgcrypto `hmac()` in SQL, or a
   post-load update). Until transform exists, raw user UUIDs sit in `stg_*` — worth restricting
   access to those schemas in the meantime.

## Next session

### 1. Preflight — done 2026-07-30

- [x] `AIRFLOW_CONN_OLAP_DB_CONN` set in `setup_env.sh`, points at `invites_dw`; dry run OK.
- [x] `uv run pytest` → 110 passed.

### 2. First committed load — done 2026-07-30

- [x] Smoke test: `tb_action_mapper` loaded 37 rows, watermark row SUCCESS.
- [x] Re-run extracted 0 rows, count unchanged — idempotency confirmed live.
- [x] All systems loaded: ichms 16 tables / 636,726 rows (~45 s), iccoli 18 / 972,918 (~33 s),
      irs 5 / 188,044 (~90 s), discovery 32 / 9,032,555 (~80 s), sibc 36 / 4,174,960 (7 m 40 s).
      One table failed on the first sibc pass — `genetic_trait_info` has Korean column names
      (`원활`, `서행`, `정체`) that the ASCII-only `quote_ident()` pattern rejected. Relaxed the
      pattern to Unicode word characters (quotes/whitespace/punctuation still rejected), reran,
      loaded cleanly. The failure path worked as designed: FAILED recorded, watermark unmoved.

### 3. Discovery — resolved by scoping, no batching needed for now

The first-load footprint was **48.9 GB**; after the scoping decisions below it is **4.55 GB across
107 tables**, and the largest single table is 881 MB. That is well within what one COPY and one
transaction handle comfortably, so batched loading is **no longer a blocker** — see "Deferred".

| Decision | Effect |
|---|---|
| `disc_lifelog_user_info` **removed from targets** — it holds every lifelog transaction and the same ground is covered by the per-measurement tables | −23.1 GB |
| `disc_lifelog_user_meal` — `exclude_columns: ("meal_data",)`, the base64 image payload; only the dietary-record history is needed | 21.3 GB → ~1.5 MB |
| `measured_dt` confirmed as the generation-date watermark for append-only history tables | no change needed |

Per system now: sibc 2.86 GB, discovery 1.02 GB, irs 356 MB, iccoli 231 MB, ichms 189 MB.
Remaining tables over 200 MB: `disc_lifelog_user_heartrate` (881 MB), `sibc.api_logs` (871 MB),
`sibc.daily_routine_activities` (776 MB), `sibc.llm_usage` (758 MB).

- [x] Watched the first `sibc` run: 7 m 40 s wall clock, no measurable temp-disk growth
      (df delta ~13 MB across the run).

### 4. Airflow — done 2026-07-30

- [x] Airflow points at the repo's `dags/` via `AIRFLOW__CORE__DAGS_FOLDER` in `setup_env.sh`
      (metadata DB in `~/airflow`, initialized with `airflow db migrate`). All 5 DAGs parse with
      no import errors and register paused. `airflow dags test elt_irs_to_staging` ran end to
      end in 9 s: 5 mapped tasks expanded, each named after its table, all incremental, all
      SUCCESS.
- [x] `SCHEDULE = None` — **decided: manual triggering only until the transform layer exists**,
      then pick a real schedule (`@hourly` is a fine starting point; the irs incremental run
      took 9 s). `MAX_PARALLEL_TABLES` stays 4.
- [x] `OVERLAP = timedelta(minutes=5)` — decided; replays are free, so the safety window costs
      only a few minutes of re-read rows per run.

### 5. OLAP layer + transform

- [ ] Settle the three caveats above (history, deletes, PII).
- [ ] Design the OLAP schema against what is actually in staging.
- [ ] Implement `transform/runner.py` and its DAG.

## Known deferrals

- **Batched loading (by bytes, not rows).** Not needed at 4.55 GB, but worth having before any
  large table returns. Note that a fixed *row count* is the wrong unit here: row widths across
  these sources span ~112 bytes to ~653 kB, so 50,000 rows means 5.6 MB for
  `disc_lifelog_user_heartrate` and 31 GB for the unfiltered meal table. The design that fits is a
  loop over **watermark windows** with a byte budget per batch, each window a full
  extract→load→commit cycle (`run_table()` already takes `upper_bound`); strict `>` lower and `<=`
  upper keeps tie boundaries correct, and it works for the keyless tables where keyset pagination
  cannot.
- **No usable index on the watermark columns of the big discovery tables.**
  `disc_lifelog_user_heartrate.measured_dt` only appears inside `(user_lifelog_sn, measured_dt)`,
  and `disc_lifelog_user_meal.ins_dt`/`upd_dt` are unindexed — so each incremental run seq-scans the
  heap. Tolerable at current sizes (heartrate's heap is 492 MB, meal's is 2.5 MB) and it is a change
  to a production source DB, so: monitor rather than act.
- **14 incremental targets have no primary key** (2 sibc, 12 discovery lifelog) — accepted as-is;
  the loader uses delete-window-then-insert for them, which is idempotent. Listed in
  `KNOWN_MISSING_PRIMARY_KEY` in `tests/extract/test_introspect.py`.
- **No linter or CI.** `pyproject.toml` has pytest configured but nothing else.
- **`apache-airflow` is pinned `~=3.2.2`** in the dev group to match the local install. Bump
  deliberately, alongside the deployed image.
- `polars` / `pandas` / `pyarrow` are still installed in `.venv` but unused and undeclared; a plain
  `uv sync` will prune them.

## Fixed along the way (context, not tasks)

- `quote_ident()` rejected non-ASCII identifiers; `sibc.genetic_trait_info` has three Korean
  column names straight from the source catalog. The pattern now allows Unicode word characters
  and still rejects everything quoting relies on (quotes, whitespace, punctuation).
- Tests that assumed an empty warehouse ("first run") broke after the first committed load; they
  now restore first-run state via `tests.db.reset_staging()` — drop the staging table and delete
  the watermark row *inside* the rolled-back transaction, so committed data is untouched.
- `stg_meta.watermarks` lookups filtered on `last_status = 'SUCCESS'`, so one failed run looked
  like a first run and silently full-reloaded the whole table.
- `iccoli.tb_loop_push_history` declared a watermark column (`update_datetime`) that does not
  exist — changed to `read_datetime` with a `create_datetime` fallback. **Worth a second look:**
  this assumes read-status updates should be captured.
- `discovery.disc_lifelog_user_food` declared `measured_dt`, which does not exist — changed to
  `ins_dt`, its only timestamp.
- `discovery.disc_lifelog_user_meal` watermarked on `ins_dt`, which never changes. 1,164 of 36,338
  rows have been edited after insert and 344 are soft-deleted, and none of that would ever have been
  picked up. Changed to `upd_dt` with an `ins_dt` fallback (`upd_dt` is NULL on 35,174 rows, so the
  COALESCE is required). **Worth a second look** — same class of judgement call as
  `tb_loop_push_history`. An audit confirmed this was the only discovery target with an update
  column its watermark ignored.
- Two duplicate target declarations removed (`tb_ext_user_preinfo`, `disc_lifelog_user_sleep_detail`);
  the second sleep_detail entry referenced a `measured_dt` column that does not exist on that table.
- Deleted the `uv init` stubs `main.py` and `src/pipeline.py` (both tracked in git, so recoverable).
