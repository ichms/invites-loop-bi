# Handover checklist

The deliverable list from `INVITES_LOOP_BI_DECISION_LOG.md` §5, with current
status. Last updated 2026-08-11.

One repo, two concerns:

- the ELT pipeline, the dbt project, the decision log and plan, the PII
  inventory — the repo root.
- **`deploy/superset/`** — the Superset compose stack, the read-only role SQL,
  dataset registration and the PI dashboard as code, and the metrics guide.

---

## Checklist

| # | Deliverable | Status | Where |
|---|---|---|---|
| 1 | dbt project (models, tests, docs) in git | **done** | `dbt/` — 34 models, **211** passing build steps |
| 2 | Deploy stack (compose, env template, role SQL) | **done** | `deploy/superset/` — pinned image, one-shot init, dashboard as code |
| 3 | Superset running, marts-only read-only role | **done (local)** | Production hosting deliberately undecided (Q-13). Planning-team role (dashboards only, no SQL Lab) still to configure |
| 4 | Verified backup restore — performed, not merely scripted | **open** | Back up the `superset_app_db_data` volume (pg_dump) and perform a restore drill |
| 5 | `SUPERSET_SECRET_KEY` stored somewhere durable | **owner action** | Currently only in the local `.env`. Must go to a password manager or Key Vault — it encrypts the stored warehouse credentials |
| 6 | `RUNBOOK.ko.md` — 이게 안 될 때 | **open** | Write against the Superset stack once ops patterns settle |
| 7 | `METRICS.ko.md` — 메트릭 추가하는 법 | **done** | `deploy/superset/METRICS.ko.md` |
| 8 | Named owner, in writing (Q-04) | **interim** | Changmin Ahn (ACH), 2026-08-06. Permanent assignment deferred — see below |
| 9 | PII inventory across all source schemas | **done** | `PII_INVENTORY.md` — 123 tables, 1,246 columns classified |
| 10 | JSONB allow-list committed + drift test wired into `dbt build` | **done** | `dbt/seeds/jsonb_allowlist.csv` + `test_jsonb_keys_in_allowlist` |

---

## Ownership (Q-04)

**Owner decision 2026-08-06: naming a permanent owner is deferred.** Changmin
Ahn (ACH) holds every operational duty in the meantime, so there is always
someone to call.

**Revisit when** — whichever comes first: handover begins, the holder changes,
or the data function is reorganised.

Whoever takes it on permanently owns:

1. The Superset containers and their application-database backups.
2. `SUPERSET_SECRET_KEY` — without it the stored warehouse credentials in a
   restored backup are unusable.
3. The dbt project: what to do when the 02:00 build fails.
4. The warehouse credentials, including rotating `superset_reader`.

---

## What a successor should read, in order

1. `CLAUDE.md` — what the repo is and how to run it.
2. `INVITES_LOOP_BI_DECISION_LOG.md` — **why** it is shaped this way. Every
   decision carries its rationale; do not reverse one silently.
3. `IMPLEMENTATION_PLAN.md` §3 — where measurement overrode the log, and why.
   This is the honest record of what turned out to be wrong.
4. `PII_INVENTORY.md` — what data exists, classified, plus the open items.
5. `dbt/docs/dbt_docs.html` — open in a browser; model and column documentation
   with the full lineage graph.
6. `HOWTO.md` — adding a dim/fact to the marts, exposing models to Superset,
   and restricting what an MCP / AI client can do.
7. `deploy/superset/README.md` and `deploy/superset/METRICS.ko.md`.

## Things that will bite

- **Percentile scores are not additive.** IRS/IRS+/LRS/MRS/PRS are 1–100
  ranks. Subtracting them produces nonsense (`IMPLEMENTATION_PLAN.md` §3.6).
- **`superset_reader` is the PII boundary, not Superset permissions.** The
  role cannot see the landing schemas at all, and that is the guarantee.
  Point Superset at the warehouse with any other account and the protection
  is gone, whatever the in-app roles say.
- **Grain tests are the contract.** When one fails, the source gained
  duplicates. Never "fix" it by deleting the test.
- **The allow-list fails safe.** A new JSONB key breaks the build on purpose;
  classify it, add it with `extract=false`, move on.
- **Enrolment waves need a watermark reset.** A user who enrols later has
  pre-enrolment iccoli rows below the watermark; delete their rows from
  `stg_meta.watermarks` to force a replay (loads are idempotent).

## Open questions carried forward

| Item | State |
|---|---|
| Q-03 existing BI tool | Never answered; would only have changed Phase 4 |
| Q-04 named owner | Deferred 2026-08-06; interim holder Changmin Ahn (ACH) |
| Q-13 production hosting | Deliberately deferred; everything is hosting-independent |
| Unmapped cohort users | 2 active members with no iccoli link — owner follow-up |
| Deployment site code | `KR_LOOP_PILOT` is a placeholder; confirm before it labels a dashboard |
| Glucose units | Normalised by threshold; a per-row unit from Discovery would retire the heuristic |
| ichms table scope | Identifier columns dropped, but no mart reads these tables at all |
| `public` schema grant | `superset_reader` holds USAGE via the `PUBLIC` pseudo-role; only an admin can revoke |
