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

### Phase 1 — dbt staging layer (Days 1–2)

- [ ] `sources.yml` over the `stg_<system>` landing schemas, with `loaded_at_field: _loaded_at`
      and source freshness thresholds — freshness is the loud-failure tripwire for a stalled
      ELT DAG, which the current stack lacks entirely.
- [ ] `stg_sibc__user_intg_log`, `stg_sibc__user_irs_log`: Q-01 dedupe (last `created_at`
      wins), `ymd` cast to `date` + cast-integrity test, JSONB flattening via **allow-list
      seed** (D-26): seed CSV `jsonb_allowlist.csv` (versioned file, per the handover
      checklist) — measured top-level keys today: `risk_overview`, `current_status`,
      `user_signature_type`, `prioritized_actions`, `disclaimers`; **`user_name` excluded**.
      Key-level flattening spec (where exactly IRS+/LRS/MRS/PRS scalars live inside
      `current_status`/`risk_overview`) is written here by inspecting payloads.
- [ ] **Drift test (D-27):** custom generic test comparing `jsonb_object_keys()` of each
      guarded payload against the seed; unknown key → build failure naming the key.
- [ ] `stg_iccoli__*`: `user_no → user_id` translation via the mapper, `ext_system_code =
      'LOOP'` filtered **inside the CTE**, `not_null` on the resulting key, singular test
      pinning the known orphan counts (§1). No model downstream of staging ever sees `user_no`.
- [ ] D-22/D-23 enforced in staging models: no username columns selected anywhere; `birth`/
      `birthday` reduced to `birth_year int` and the raw column never selected.
- [ ] **Q-11 inventory** (`analysis/pii_inventory.md`): every column in all five landing
      schemas classified identifier / quasi-identifier / analytical. Seeded by §2.
- [ ] Tests throughout: `not_null` + null-rate threshold test (D-05) on every JSONB-extracted
      field.

### Phase 2 — core marts (Days 3–5) — *load-bearing; if only this ships, handover still works*

- [ ] `dim_user` (SCD1, D-08): population = `sibc.user_master` per N-02, plus `is_mapped`
      flag; `user_id`, sex, `birth_year`, `joined_dt`, site FK, device allocation flag.
      Attribute list finalised against driver-tree Layer 2 (Q-06) — start minimal, widen on
      demand.
- [ ] `dim_date` (generated), `dim_disease` (35 rows from `IRSdiseasecatalog.csv` as a dbt
      seed — KOR+ENG phenotype labels), `dim_action`, `dim_deployment_site` (one row, built
      anyway per D-10's rationale).
- [ ] `fct_user_day` (user × ymd): scalar IRS+/LRS/MRS/PRS + explicit residual column;
      `age_at_activity` per D-24 formula **and `age_band_5y`** materialised (Q-12: the band is
      what Metabase surfaces; raw age stays for view-layer computation).
- [ ] `fct_user_disease_day` (user × ymd × disease_id): `risk_overview[]` explosion, kept
      separate from `fct_user_day` per the log's explicit warning.
- [ ] **Grain tests on every fact** (`dbt_utils.unique_combination_of_columns` on the declared
      grain key; grain declared in a header comment). Never cut.

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
| N-01 PII at EL boundary | **Decided (a) and implemented 2026-08-06** — §3.4 and Phase 0 |
| N-02 cohort scoping | **Decided (row_filter at EL) and implemented 2026-08-06** — §3.4 |
| **NEW: unmapped active cohort user** | uuid `2725eece…` — real member, no iccoli mapping. Owner follow-up required (Phase 0 notes) |
