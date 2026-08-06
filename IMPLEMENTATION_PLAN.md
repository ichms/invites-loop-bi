# INVITES_LOOP_BI — Implementation Plan

**Version:** v1.0
**Date:** 2026-08-06
**Companion to:** `INVITES_LOOP_BI_DECISION_LOG.md` v0.3 — this plan executes it. Where this
document proposes changing a decision, the conflict is stated explicitly (§3), per the log's
own rule against silent reversal.
**Status of blockers:** Q-01 and Q-10 were resolved **by measurement** on 2026-08-06 (§1).
The Q-11 assumption was tested and is **false** (§2). Day 1–2 work is unblocked.

---

## 1. Diagnostics run 2026-08-06 — Q-01 and Q-10 resolved

Read-only queries against the live sources (`iccoli`, `invites_loop`) and the warehouse
(`invites_dw`). Rerun-able; every number below is current as of today.

### Q-10 — canonical user key → **elect `invites_loop.user_id`. Confirmed.**

`iccoli.public.tb_ext_user_mapper` is `(user_no int, ext_system_code varchar, ext_user_uuid uuid, create_datetime)`:

| Check | Result |
|---|---|
| Cardinality | 441 rows, 441 distinct `user_no`, 441 distinct `ext_user_uuid` — **strict 1:1**, no fan-out |
| System codes | Single value `LOOP` — but the column exists, so the mapper is *designed* to fan out per system later. Any join must filter `ext_system_code = 'LOOP'`. |
| Directionality | iccoli holds **1,283** users; only 441 are mapped. iccoli is the broad app-account population; the mapper is iccoli's pointer *out* to the Loop cohort. This confirms the log's provisional argument: `user_id` is the cohort-native key. |
| Orphans, cohort side | `sibc.user_master` holds **404** users; **403 map, 1 does not**. That one user must be identified (test account vs. genuine cohort member) during Phase 1 — it will silently miss all app-action joins otherwise. |
| Orphans, app side | 842 of 1,283 iccoli users unmapped — expected (non-cohort app users). They must be *filtered and counted*, never silently dropped (join-hygiene rule in the log's Q-10 notes). |

**Consequences implemented in this plan:** translation happens once, in `stg_iccoli__*` staging
models, filtered `ext_system_code = 'LOOP'` inside the CTE; `not_null` test on the translated
key; a singular test asserting the unmapped-cohort-user count is a known number (currently 1),
so a regression is loud.

### Q-01 — `fct_user_day` grain → **not clean; deterministic dedupe rule exists. Resolved.**

`sibc.user_intg_log` and `sibc.user_irs_log` (both `user_id uuid, ymd varchar, payload jsonb, created_at, updated_at`):

| Check | Result |
|---|---|
| Rows vs. distinct `(user_id, ymd)` | 6,481 vs. 5,520 in **both** tables — identical counts, so the two logs are paired writes; one dedupe rule serves both |
| Duplicate groups | 715 groups, up to **22 rows** per user-day |
| `created_at` within groups | Distinct in **all 715** groups → ordering is total, dedupe is deterministic |
| Payloads within groups | Differ in **all 715** groups → genuine intra-day recomputations, not replayed identical rows |

**Rule:** last-row-wins — `row_number() over (partition by user_id, ymd order by created_at desc) = 1`
in staging, then a `unique` grain test on `(user_id, ymd)` *after* dedupe (D-04). The same rule
applies to both logs; the grain test is what catches the day this stops being true.

**Found in passing, must be handled in staging:** `ymd` is `character varying`, not `date`.
Staging casts it and a test asserts the cast never nulls out (`ymd is not null → ymd_date is not null`).

---

## 2. Q-11 tested — the "already anonymised" assumption is **false**, and PII is already in the warehouse

The decision log's §2.5 places minimisation at the T boundary on the reasoning that "data that
never enters `stg_*` cannot leak downstream." That reasoning is correct — but the EL pipeline's
landing schemas are *also* named `stg_*`, and they already contain direct identifiers today:

| Warehouse location | Contents | Severity |
|---|---|---|
| `stg_iccoli.tb_user_personal_info` (1,280 rows) | **`ci`, `di`, `name`, `birth`, `phone`, `email`, `telecom`** | Direct identifiers incl. CI/DI — the exact fields Q-11 worried about |
| `stg_iccoli.tb_ext_user_preinfo` | `name`, `phone`, `local_phone`, `birth` | Direct identifiers |
| `stg_iccoli.tb_user_device_info` | `device_token`, `apns_*_token`, `game_token` | Device identifiers |
| `stg_sibc.user_master` | `user_nm`, `birthday`, `birthtime`, static `age` | Direct + quasi-identifiers; the static `age` column is exactly what D-24/D-25 exist to avoid — never source age from here |
| `stg_sibc.user_intg_log.intg_anlys` | top-level JSONB key **`user_name`** | Validates D-26: the allow-list must exclude it |
| `stg_ichms.auth_user*`, `mem_user`, `mem_family*` | auth/identity layer, extracted wholesale (16 tables incl. `auth_user_profile`, `auth_user_login_history`) | Unclassified — inventory required |
| `stg_sibc.chat_msgs`, `stg_discovery.disc_genomic_user_info`, `disc_dtc_user_info` | free-text health chat; genomic data | Sensitive categories; must never reach marts |

**New decision required — N-01 (owner: ACH, decide before Phase 1):**
where does PII minimisation actually happen, given EL already lands everything?

- **(a) Recommended: minimise at the EL boundary too.** Add `exclude_columns` support to the
  target config + extractor/loader (introspection already builds the column list, so this is a
  filter at plan time — small, testable change), drop the flagrant tables/columns from the
  target lists (`tb_user_personal_info`'s `ci/di/name/phone/email/telecom`,
  `tb_ext_user_preinfo` entirely, device-token columns), and `ALTER TABLE ... DROP COLUMN` /
  `DROP TABLE` the already-landed copies. Keep only what marts need (`birth` → reduce to
  `birth_year` at dbt staging per D-23, `gender`). This applies §2.5's own principle at the
  boundary it was written for.
- **(b) Fallback if (a) is cut for time:** rely on role separation — `bi_reader` is marts-only
  (D-16), so Metabase never sees these — and record in the PII inventory that raw identifiers
  persist in warehouse landing schemas, reachable by anyone with warehouse credentials and
  present in every warehouse backup. This is a documented hole, not a policy.

Either way, the **full Q-11 inventory** (enumerate + classify every column across all five
landing schemas) is scheduled in Phase 1 and lands as `analysis/pii_inventory.md` — the
half-day the log asked for, now seeded by the findings above.

---

## 3. Proposed amendments to the decision log

Surfaced explicitly per the log's §6 rule. None reverses a rationale; two simplify, one renames.

1. **Q-05 (incremental strategy) → resolve as "no incremental models at all."** Measured
   volumes: the largest sibc log is 6.5k rows; the `risk_overview` explosion is ~230k rows
   today, ~5M/yr projected. A nightly full rebuild of 5M rows in Postgres is minutes. Every
   model materialises as `table`; revisit only if `dbt build` exceeds ~15 minutes. This deletes
   the late-arriving-data window problem, the per-model watermark decisions, and the hardest
   dbt concept the junior would otherwise inherit. Strictly aligned with the governing
   constraint (fewer moving parts).
2. **Schema layout (new decision, forced by a naming collision the log doesn't cover):** the
   log's architecture diagram labels dbt's first layer `stg_*`, but `stg_<system>` is already
   the EL landing layer in the warehouse. Proposal: **landing schemas stay `stg_<system>`**
   (no churn in a working pipeline); dbt staging models are **views in a new `staging` schema**
   (files named `stg_<system>__<table>.sql` per dbt convention); dims/facts/metric views are
   **tables+views in a new `marts` schema**. `bi_reader` is granted `marts` only — one schema,
   one grant, matching D-16/D-17. The dbt README states the landing-vs-staging distinction in
   its first paragraph.
3. **D-02 refinement:** there are five L DAGs, not one, so "`dbt build` at the end of the L
   DAG" needs a concrete shape: a sixth DAG `transform_dbt_build` (single `BashOperator`,
   `dbt build --fail-fast`) scheduled after the ELT DAGs — Airflow 3 asset-triggered off the
   five, or a fixed time offset (ELT 01:00 KST, transform 02:00 KST) if asset wiring proves
   fiddly; the offset is easier to explain in the runbook. ELT DAGs get their real schedule at
   the same time (currently `SCHEDULE = None`).

4. **N-02 — cohort scoping (decided 2026-08-06, IMPLEMENTED): community users never leave
   the source system.** The owner chose the stronger, consent-safe variant: an optional
   `row_filter` predicate in the target config, applied **at extraction** — every user-keyed
   iccoli table (15 of them) now extracts only rows matching
   `user_no IN (SELECT user_no FROM public.tb_ext_user_mapper WHERE ext_system_code = 'LOOP')`
   (`LOOP_USERS_ONLY` in `iccoli_targets.py`). The filter lives in the extraction query only,
   never in `ExtractionPlan.predicate` (which the loader replays against staging for
   keyless-table deletes, where the mapper subquery would not resolve). Already-landed
   community rows (~101k) were purged by `scripts/20260806_pii_cleanup.sql`.
   **Enrolment-backfill caveat:** a later-enrolled user's pre-enrolment rows sit below the
   watermark and are not re-read on their own; after an enrolment wave, delete the iccoli
   rows from `stg_meta.watermarks` — loads are idempotent, so the full replay is safe. Goes
   in the runbook.
   **Cohort population = `sibc.user_master`** (404 rows, grain verified unique on `user_id`),
   *not* the mapper. The 39 mapper-only entries have no sibc presence and therefore no facts;
   they are counted, not modelled. `dim_user` carries an `is_mapped` flag so the 1 unmapped
   cohort user keeps their sibc facts instead of being orphaned.
6. **The log's "explicit residual term" on `fct_user_day` is retired (measured 2026-08-06).**
   The log's model table says to carry the residual as a column, which assumes
   `IRS ≈ PRS + LRS + MRS + residual`. All five values are integer **percentile ranks**
   (1–100, zero decimal places, verified across 147k rows), and per `IRS-03` the IRS is an
   ML combination of PRS, updated LRS and updated MRS, with IRS+ adding other diseases'
   MRS. `IRS − (PRS+LRS+MRS+IRSp)` averages **−135** with a 42-point spread — an artefact,
   not a decomposition. There is nothing to carry, so no residual column exists. Nothing
   else in the log's rationale depends on it. Any future "how much of the risk is
   lifestyle-driven" question is a modelling request to the IRS team, not a subtraction.
7. **`fct_user_disease_day` is built from `stg_irs.user_irs_hist`, not the `risk_overview[]`
   explosion (measured 2026-08-06).** The payload's per-disease `irs_rank` **is** the IRS+
   score — it equals `irsp_score` on 12,806 of 12,900 matched user-day-disease rows (99.3%).
   The relational table carries all five scores, typed, at an exactly verified grain, so
   exploding the payload would re-derive one column and lose four. The payload remains the
   source for narrative content (symptoms, care factors) if a model ever needs it.
5. **`tb_ext_user_mapper` is now a full-refresh target (found and fixed 2026-08-06).** The
   warehouse briefly held 442 mapper rows while the live source held 441: a mapping had been
   *deleted* upstream, and an incremental load never propagates deletes — a stale mapper row
   is precisely the row that silently corrupts cohort membership. At ~450 rows,
   truncate-and-reload costs nothing and keeps membership exact. (General lesson, noted for
   Phase 1: incremental staging tables reflect deletes for no table; the mapper was just the
   place where it bites hardest. Source freshness + count tests cover the rest.)

---

## 4. Phase plan (~2 weeks from 2026-08-06)

Mirrors the log's §2.6 sequencing, adjusted for the findings above. Each phase ends at a
working state; the log's cut order applies unchanged (metric views first, then dashboards,
then remaining facts; **never** the grain tests).

### Phase 0 — decisions + scaffold (Day 0–1) — **DONE 2026-08-06**

- [x] **N-01 decided as (a) and implemented.** `exclude_columns` already existed end-to-end
      (config → introspection → SELECT/DDL/merge); `row_filter` added (§3.4). Targets pruned:
      `tb_ext_user_preinfo` removed; `tb_user_personal_info` excludes
      `ci, di, name, phone, email, telecom` (keeps `birth` as the single source of
      `birth_year`); `tb_user_device_info` excludes the token/device identifiers. Landed PII
      dropped and ~101k community rows purged (`scripts/20260806_pii_cleanup.sql`, executed).
      Full suite green (117 tests).
- [x] **Unmapped `user_master` user identified as a real cohort member, not a test account**
      (uuid `2725eece…`, joined 2026-05-01, active through 2026-08-03, 7 scoring rows, name
      matches no test pattern). They have sibc facts but no iccoli mapping, so app-action
      joins will miss them. **Owner follow-up: why does an active cohort member have no
      iccoli link?** `dim_user.is_mapped` keeps them modelled either way.
- [x] dbt scaffolded in `dbt/`: dbt-core 1.10.22 + dbt-postgres 1.9.1 pinned in the
      `transform` dependency group; `dbt debug` and an empty `dbt build` pass against the
      warehouse. `transform/runner.py` replaced with a pointer comment.
- [x] `profiles.yml` env-var based; `setup_env.sh` exports `DBT_PROFILES_DIR` + `DBT_PG_*`.
- [x] `generate_schema_name` macro pins the layout: sources = `stg_<system>`, dbt staging
      views = `staging`, marts = `marts` (READMEs in `dbt/models/*` explain the naming).

### Phase 1 — dbt staging layer (Days 1–2) — **DONE 2026-08-06** (`dbt build`: 58/58 green; `dbt source freshness`: 9/9 pass)

- [x] Source declarations over all five landing schemas (123 tables), one file per system
      (`dbt/models/staging/src_*.yml`), `loaded_at_field: _loaded_at`. Freshness is **opt-in
      per table**, not blanket — a quiet incremental table would false-alarm and teach people
      to ignore the tripwire. Two signals per system: a *full-refresh* table (loader rewrites
      it every DAG run, so staleness = "the DAG did not run") and a daily heartbeat event
      table where one exists. Found in passing: `disc_globalization_code` is empty at the
      source (0 rows), so its `max(_loaded_at)` is always NULL — the discovery tripwire is
      `disc_user_disease_answer` instead.
- [x] `stg_sibc__user_intg_log`, `stg_sibc__user_irs_log`: Q-01 dedupe, `ymd` cast (+
      not_null as the cast-integrity test; `to_date` raises on garbage, loudly), flattening
      via `dbt/seeds/jsonb_allowlist.csv`. The seed distinguishes **known** keys from
      **extracted** keys (`extract` flag): a key must be listed to pass the drift test and
      flagged to leave the payload — `user_name` is known-and-never-extracted. Measurement
      added one key the plan's list missed: **`error`** (1 row, an LLM serialisation failure
      `{"error": "..."}` with no structured fields; staging filters such rows,
      `assert_intg_error_rows_bounded` warns if the count grows).
      **Flattening spec, corrected by measurement:** the scalar IRS+/LRS/MRS/PRS scores are
      **not in the sibc payloads at all** — they live relationally in
      `stg_irs.user_irs_hist` (`irs/irsp/lrs/mrs/prs_score` at (user_id, create_date,
      disease_id), grain verified exact, 180,969 rows, **44** disease ids — note: not 35;
      check against `IRSdiseasecatalog.csv` before seeding `dim_disease` in Phase 2). A new
      `stg_irs__user_irs_hist` model stages them. The payloads carry per-disease `irs_rank`
      (`risk_overview[]`, passed through as jsonb for the Phase 2 explosion) and
      `user_signature_type` (flattened to `signature_*` columns). `user_irs_log.irs_data` is
      never selected: legacy mixed-shape, and its 467 object-form rows carry `USERNAME` (see
      PII_INVENTORY.md).
- [x] **Drift test (D-27)** (`tests/generic/test_jsonb_keys_in_allowlist.sql`) attached to
      both payload columns at the *source* level — drift is caught before staging runs.
- [x] `stg_iccoli__*` (mapper, user_personal_info, user_info, action_info, action_user_log,
      user_login_log): translation CTE filtered `ext_system_code = 'LOOP'` inside, `not_null`
      on the translated key, no `user_no` downstream of staging. Orphan pins:
      `assert_unmapped_cohort_users_pinned` — **the count moved since §1 was written: 2, not
      1**. New unmapped-but-active cohort member `fbe82bc5…` (joined 2026-05-01, same day as
      `2725eece…`); same owner follow-up. `assert_mapper_only_users_counted` warn-pins the
      39 mapper-only entries.
- [x] D-22/D-23 enforced: no name/nickname column selected anywhere; `birth` ('YYMMDD',
      two-digit year → century pivot on current year) reduced to `birth_year int`, raw value
      never selected; `user_master` staging selects only `user_id, sex, joined_dt, timezone`
      + timestamps.
- [x] **Q-11 inventory** delivered as **`PII_INVENTORY.md` (repo root)** — `analysis/` is
      gitignored as local scratch and this is a versioned handover deliverable, hence the
      placement change. All 123 tables / 1,246 columns classified. Findings exceed §2:
      `auth_user_account.login_pw` (16k bcrypt hashes), `tb_loop_push_history.push_token`
      (236k rows, N-01 missed it), phone numbers in the coupon SMS trail, relational
      `user_name` columns in `target_calorie`/`user_profiles_log`, `USERNAME` inside legacy
      `irs_data` payloads. Recommendations R-1..R-8 are owner decisions (N-01 policy), not
      config edits made here.
- [x] Tests: 47 data tests green — grain tests on every staging model with a declarable
      grain, D-05 not_null + `null_rate_below` pairs on every JSONB-extracted field
      (thresholds pinned to measured baselines, e.g. scores ~19–23% null → 0.35 ceiling).

### Phase 2 — core marts (Days 3–5) — **DONE 2026-08-06** (`dbt build`: 110/110 green)

- [x] `dim_user` (SCD1, D-08): 404 rows, population = `sibc.user_master` per N-02, with
      `is_mapped` (402 true / 2 false), `sex`, `birth_year` (400 non-null), `joined_dt`,
      `site_id` FK, plus app-account `channel_type`/`status`. **Device-allocation flag
      omitted, not forgotten:** no source system in any of the five landing schemas carries
      one (checked 2026-08-06). Deriving it from measurement activity would be a metric
      definition disguised as a dimension attribute — it belongs in a `v_pi_*` view if it is
      ever needed. Q-06 stays open for the rest of the attribute list; start minimal held.
- [x] `dim_date` (generated, 1,095 rows, 2025-01-01 → end of next year, Monday weeks per
      D-18), `dim_disease` (35 rows, seeded from `docs/01_product_specs/IRS-disease-catalog.csv`
      — **the source file is CRLF; strip it or every id gains a trailing `\r` and joins fail
      silently**), `dim_action`, `dim_deployment_site` (one row; the site code is a
      placeholder — owner to confirm before it reaches a dashboard label).
- [x] `fct_user_day` (user × ymd, 5,747 rows). **Union spine, not an inner join:** 4,299
      user-days have both signals, 1,199 have only the integrated analysis, 249 only IRS
      scores — an inner join would have silently dropped ~1,400 user-days. `has_intg_analysis`
      / `has_irs_scores` expose the asymmetry as columns. `age_at_activity` (D-24 July-1
      anchor) **and** `age_band_5y` (Q-12) materialised; measured range 21.8–87.1, 14 bands.
      **No residual column** — see §3.6.
- [x] `fct_user_disease_day` (user × ymd × disease, 180,969 rows — exactly the source count;
      150,084 in-catalog). Built from `stg_irs__user_irs_hist`, not the payload explosion —
      see §3.7. `is_in_catalog` separates the 35 user-facing diseases from the 9 scored-only
      ones, so the fact stays complete while every disease-sliced metric filters or joins the
      dim.
- [x] **Grain tests on both facts** (`unique_combination_of_columns`, grain declared in each
      header comment), plus `relationships` tests on every FK — the dim_disease one scoped
      `where: is_in_catalog` because the 9 extras have no dim row by design.

### Phase 3 — remaining facts + orchestration (Days 6–7)

- [ ] `fct_coaching_event`, `fct_measurement` (with `device_type` FK), `fct_app_action`
      (the one model needing key translation — already done in its staging model).
- [ ] `transform_dbt_build` DAG (§3.3); real schedules on the five ELT DAGs; `--fail-fast` so
      a broken grain stops the build loudly (governing constraint, corollary 1).
- [ ] `dbt docs generate --static` → single self-contained HTML, committed per release (Q-07:
      findable = in the repo the junior already has; no hosting dependency).

### Phase 4 — Metabase, locally (Days 8–10)

- [ ] `invites-loop-bi-deploy` repo, exactly the log's layout (D-20/D-28). Local note: this
      machine runs Docker via **Colima**, not Docker Desktop — the compose file needs nothing
      special, but the runbook's local-dev section should say `colima start` first.
- [ ] Pinned Metabase tag (D-14), postgres app-DB container (D-13), env vars per D-18
      (`MB_REPORT_TIMEZONE=Asia/Seoul` — KST correctness, not cosmetics).
- [ ] `01_readonly_role.sql`: `bi_reader`, `GRANT USAGE ON SCHEMA marts` + `SELECT` on its
      tables only, `ALTER DEFAULT PRIVILEGES` so new marts models are covered. Blocked-by:
      Q-09 (does `grmc` share the instance) — ask now, decide before writing the file.
- [ ] Permission groups: Planning Team = query builder on marts, **native SQL off** (D-17).
- [ ] `backup.sh` / `restore.sh`; **restore actually performed** against a scratch container
      (D-15) and the run recorded in the runbook.
- [ ] Three dashboards that demonstrate the pattern (per the log's §4.5 scope rejection).

### Phase 5 — metric views + handover (Days 11–14)

- [ ] `v_kpi_*` / `v_pi_*` / `v_bridge_*` views in `marts`, one metric per view, tier prefix
      mandatory (D-10; the KPI/PI/Bridge separation is load-bearing).
- [ ] `RUNBOOK.ko.md`, `METRICS.ko.md` (Korean, per language convention).
- [ ] Named owner in writing (Q-04) — chase in parallel from Day 0; it is the plan's only
      item with an external dependency and the log calls it the most likely failure mode.
- [ ] Handover checklist from the log's §5, including the PII inventory and the versioned
      allow-list.

---

## 5. Remaining open items (unchanged from the log, with plan hooks)

| Item | Status here |
|---|---|
| Q-03 existing BI tool | Ask Planning/IT during Phase 0 — answer changes Phase 4 only |
| Q-04 named owner | Chase from Day 0; deliverable in Phase 5 |
| Q-06 dim_user attributes | Finalised in Phase 2 against the driver tree |
| Q-08 Jeju/Mode C placeholders | Follow log recommendation: omit from marts, document in Bridge Register |
| Q-09 grmc co-tenancy | Must be answered before `01_readonly_role.sql` (Phase 4 gate) |
| Q-12 age exposure | Plan implements the log's recommendation (band in marts, raw age view-layer only) |
| Q-13 production hosting | Untouched; everything here is hosting-independent per D-28 |
| N-01 PII at EL boundary | **Decided (a) and implemented 2026-08-06** — §3.4 and Phase 0. Phase 1's full inventory found gaps in the pruning: see `PII_INVENTORY.md` R-1..R-8, all owner decisions |
| N-02 cohort scoping | **Decided (row_filter at EL) and implemented 2026-08-06** — §3.4 |
| **NEW: unmapped active cohort users** | Now **two**: `2725eece…` (Phase 0) and `fbe82bc5…` (Phase 1) — both real members, both joined 2026-05-01, no iccoli mapping. Owner follow-up required; `assert_unmapped_cohort_users_pinned` fails loudly if the set changes |
| **NEW: dim_disease row count** | **Reconciled 2026-08-06:** all 35 catalog diseases are scored, plus exactly 9 scored-but-not-displayed extras (macular degeneration, brain aneurysm, cardiac arrhythmia, endometrial cancer, endometriosis, hepatocellular carcinoma, lung cancer, Parkinson's, PCOS). Owner: focus stays on the 35 — `dim_disease` seeds from the catalog; fact rows for the 9 simply don't join to the dim and are not user-facing |
| **NEW: `login_pw` in warehouse** | **Resolved 2026-08-06:** owner decided to discard the direct-identifier classes; `scripts/20260806_pii_cleanup_phase1.sql` (executed) dropped 26 columns across ichms/sibc/iccoli and stripped name keys from frozen legacy payloads; matching `exclude_columns` added to all three target configs. Remaining open items in PII_INVENTORY.md §Resolution status (ichms table-scope question, R-7, R-8, upstream `user_name` key) |
