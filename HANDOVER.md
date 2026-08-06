# Handover checklist

The deliverable list from `INVITES_LOOP_BI_DECISION_LOG.md` §5, with current
status. Last updated 2026-08-06.

Two repos:

- **`invites-loop-bi`** (this one) — the ELT pipeline, the dbt project, the
  decision log and plan, the PII inventory.
- **`invites-loop-bi-deploy`** (sibling) — Metabase compose stack, the
  read-only role SQL, backup/restore scripts, and the Korean operating docs.

---

## Checklist

| # | Deliverable | Status | Where |
|---|---|---|---|
| 1 | dbt project (models, tests, docs) in git | **done** | `dbt/` — 18 models, 184 passing build steps |
| 2 | Deploy repo (compose, env template, role SQL, backup/restore) | **done** | `../invites-loop-bi-deploy` |
| 3 | Metabase running, marts-only read-only role, permission groups | **done (local)** | Production hosting deliberately undecided (Q-13) |
| 4 | Verified backup restore — performed, not merely scripted | **done** | 2026-08-06; 4 dashboards / 11 questions / 4 groups recovered |
| 5 | `MB_ENCRYPTION_SECRET_KEY` stored somewhere durable | **owner action** | Currently only in the local `.env`. Must go to a password manager or Key Vault |
| 6 | `RUNBOOK.ko.md` — 이게 안 될 때 | **done** | `../invites-loop-bi-deploy/RUNBOOK.ko.md` |
| 7 | `METRICS.ko.md` — 메트릭 추가하는 법 | **done** | `../invites-loop-bi-deploy/METRICS.ko.md` |
| 8 | **Named owner, in writing (Q-04)** | **interim** | Changmin Ahn (ACH), provisionally, 2026-08-06. Permanent owner deferred by decision — see below |
| 9 | PII inventory across all source schemas | **done** | `PII_INVENTORY.md` — 123 tables, 1,246 columns classified |
| 10 | JSONB allow-list committed + drift test wired into `dbt build` | **done** | `dbt/seeds/jsonb_allowlist.csv` + `test_jsonb_keys_in_allowlist` |

---

## The one that matters most (Q-04) — deferred, with an interim holder

**Owner decision 2026-08-06: too early to name a permanent owner.** Until then,
Changmin Ahn (ACH) holds every line in the `RUNBOOK.ko.md` §6 table.

That closes the "nobody knows who to call today" problem and leaves the real one
open, so state it plainly: **the interim holder is the person handing this over
and leaving.** An owner table naming the departing author is, on the day they
leave, an empty table. This is a deferral, not a resolution.

**Revisit trigger** — whichever comes first:

1. handover begins, or
2. the current holder's departure is confirmed, or
3. any reorganisation that changes who runs the data function.

The decision log calls this the most likely failure mode of the whole effort,
and nothing in five phases of work changed that — it is the only item here that
cannot be solved by writing code.

Concretely, the permanent owner must own:

1. The Metabase container and its application-database backups.
2. `MB_ENCRYPTION_SECRET_KEY` — without it the backups are unrestorable.
3. The dbt project: what to do when the 02:00 build fails.
4. The warehouse credentials, including rotating `bi_reader`.

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
6. `../invites-loop-bi-deploy/RUNBOOK.ko.md` and `METRICS.ko.md`.

## Things that will bite

- **Percentile scores are not additive.** IRS/IRS+/LRS/MRS/PRS are 1–100
  ranks. Subtracting them produces nonsense (`IMPLEMENTATION_PLAN.md` §3.6).
- **`bi_reader` is the PII boundary, not Metabase permissions.** Metabase's
  data-blocking permission is an Enterprise feature. Point Metabase at the
  warehouse with any other account and the protection is gone.
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
| Q-04 named owner | **Deferred 2026-08-06**; interim holder Changmin Ahn (ACH). Still blocking for handover — see the revisit trigger above |
| Q-13 production hosting | Deliberately deferred; everything is hosting-independent |
| Unmapped cohort users | 2 active members with no iccoli link — owner follow-up |
| Deployment site code | `KR_LOOP_PILOT` is a placeholder; confirm before it labels a dashboard |
| Glucose units | Normalised by threshold; a per-row unit from Discovery would retire the heuristic |
| ichms table scope | Identifier columns dropped, but no mart reads these tables at all |
| `public` schema grant | `bi_reader` holds USAGE via the `PUBLIC` pseudo-role; only an admin can revoke |
