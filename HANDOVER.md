# Recovery and operations handover

Last updated: 2026-08-21 KST

This is the handover for the current W-first mart redesign and safe recovery. It
is not a claim that the previous marts are operational. [todo.md](todo.md) is
the execution authority; this file summarizes what a successor needs to know
and which decisions still require an owner.

## Current handover state

- The configured EL estate has 128 targets and all 128 watermark rows currently
  report <code>SUCCESS</code>.
- EL was last completed manually through the 2026-08-21 08:00 KST source
  cutoff.
- P3 targeted builds restored the redesigned dimensions and atomic facts plus
  2,744 lifecycle milestones, 81,745 user-days, and 2,996 user-months. This was
  not the complete <code>daily_core</code> recovery. Six raw wearable facts
  remain empty in <code>marts_detail</code>; legacy metric views have not passed
  P5 acceptance.
- The local Superset stack and its historical datasets/dashboard still exist,
  but no refresh or representative-chart acceptance was run after P3. Existing
  dataset output must not be treated as approved operating evidence.
- The prior dbt 388/388 and pytest 125/125 results describe an older graph.
  They are not recovery acceptance criteria.
- The current offline Python baseline is 95 passed and 32 skipped. The live
  suite has not been rerun.
- No scheduler is deployed. The declared Airflow schedules have never operated
  the pipeline unattended.
- P0 through P4 are complete and recovery is at P5. The
  <code>daily_core</code> and <code>wearable_detail</code> selectors plus
  <code>intermediate_private</code>/<code>marts_detail</code> access boundaries
  are implemented and verified. The lifecycle/panel redesign and reusable
  heart-rate dedupe are implemented; the metric registry and W-A/B/C/D layer
  remain.

Do not quote Superset or legacy metric views as current business evidence.

## Preserve before proceeding

The 2026-08-21 baseline commit is <code>35b0ed4</code>. The following
pre-existing uncommitted work is part of the redesign:

| File | Intended change |
|---|---|
| <code>.gitignore</code> | Make <code>todo.md</code> trackable |
| <code>dags/elt_to_staging.py</code> | Update the iccoli target count from 34 to 37 |
| <code>src/invites_loop_bi/config/iccoli_targets.py</code> | Add search/share targets and actor filtering |
| <code>tests/extract/test_config_targets.py</code> | Add cohort-filter and initial PII checks |
| <code>todo.md</code> | Record the recovery contract |

A successor must inspect <code>git status --short</code> and the relevant diffs
before editing. Do not revert, overwrite, commit, push, deploy, or clean these
changes without explicit authorization.

The three new targets are filtered full-refresh targets with complete EL
exclusions. The reviewed P0 migration removed the previously landed prohibited
columns without changing rows or watermarks. P1 staging projections and atomic
facts preserve that contract; do not relax it in P2 or later phases.

## Read in this order

1. [todo.md](todo.md) — active gates, stop rules, and completion criteria.
2. [AGENTS.md](AGENTS.md) — repository architecture and stable engineering
   rules.
3. [INVITES_LOOP_BI_DECISION_LOG.md](INVITES_LOOP_BI_DECISION_LOG.md) —
   decisions and rationale, subject to the authority order above.
4. [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — dated measurements and
   assumptions that measurement overturned.
5. [PII_INVENTORY.md](PII_INVENTORY.md) — the post-P0 128-target structural
   snapshot, search/share cleanup evidence, and retained policy questions.
6. [HOWTO.md](HOWTO.md) — safe recipes for target, model, metric, permission,
   and Superset changes.
7. [deploy/superset/README.md](deploy/superset/README.md) — local viewer stack
   details. Do not treat local availability as production readiness.
8. After P6, generate dbt docs and review
   <code>dbt/target/static_index.html</code> for the actual recovered graph.

## Non-negotiable safety rules

Until P0 through P5 are complete:

- no bare or full-graph dbt build;
- no scheduler activation;
- no global Superset marts registration;
- no new landing truncation, deletion, or manual watermark deletion;
- no large or wearable-detail execution without Azure storage measurement;
- no historical attribution from current site;
- no commit, push, or deployment unless separately requested.

A narrow model build is allowed only after its exact <code>dbt ls</code>
selection is reviewed, with one thread and fail-fast, and only when the
selection excludes the heart-rate/detail path.

The current transform DAG is not production-safe. It runs the full graph,
ignores freshness failure, does not limit threads, and blindly retries the
whole build. Do not unpause or deploy it as written.

## Recovery phases and exit gates

The full checklists live in [todo.md](todo.md). The phase boundary matters more
than the calendar.

| Phase | Work | Exit evidence |
|---|---|---|
| P0 | Preserve diffs; convert three new sources to filtered full refresh; add EL exclusions; prepare reviewed landing cleanup; regenerate the PII inventory | Target config and inventory agree; prohibited fields cannot re-land; offline tests pass |
| P1 | Add dbt sources, staging, actor translation, and three atomic event facts | Measured source unique-index grains, Loop-only actors, PII absence, share denominators, and row-loss reconciliation pass |
| P2 | Add <code>daily_core</code> and <code>wearable_detail</code> selectors; separate <code>marts</code>, private intermediates, and <code>marts_detail</code>; enforce grants | Core selection excludes all raw detail; general BI role cannot read detail; builds are independent |
| P3 | Shrink <code>dim_user</code>; separate current site and milestones; rebuild dense daily/month panels from canonical facts; model channel completeness | No future leakage; current versus historical site is explicit; channel totals reconcile; unknown is not false zero |
| P4 | Materialize reusable heart-rate dedupe; add bounded incremental/window replacement and full-refresh comparison | Heavy aggregation is computed once; weighted daily values and source-row counts reconcile; core does not rebuild detail |
| P5 | Add the metric registry and W-A/B/C/D semantic views | Every public metric has evidence and provenance, population scope, entity, grain, numerator, denominator, eligibility, censoring, owner, and freshness; representative views are non-empty |
| P6 | Run measured recovery after all prior gates; rebuild core; test; generate docs; explicitly refresh Superset | Current graph is green; storage/runtime baseline is recorded; current charts return data; PII/detail access is denied |
| P7 | Add real five-EL dependency, hard freshness/storage gates, durable scheduler and metadata, alerts, backups, and an English runbook | The pipeline operates without a local machine; failures identify source, freshness, storage, and dbt node; responsibilities are written |

A later phase's database mutation must not start before the preceding phase's
exit evidence exists.

P3 exit evidence was recorded on 2026-08-21 KST: exact one-thread targeted
builds excluded the raw heart-rate/detail path; 201 P3 core tests passed; the
437-user current-site bridge is exactly one-to-one; atomic totals reconcile to
the 81,745-row daily panel; and the 2,996-row monthly panel carries observed-day
denominators plus left-partial/right-censored flags. Per-target watermarks are
explicitly labelled <code>TARGET_SUCCESS_ONLY</code>, not DAG completion. New
core tables inherited <code>superset_reader</code> SELECT while private/detail
relations remained denied.

P4 exit evidence was recorded on 2026-08-21 KST. Azure storage measured 51.87%
before execution, peaked at 52.43%, and ended at 51.86%. The canonical private
dedupe contains 9,010,144 distinct payloads representing 9,010,635 source rows;
491 exact duplicate rows remain visible through <code>source_row_count</code>.
The full build took 68.32 seconds and the 30-day replacement took 58.33 seconds.
The full-source equivalence audit passed after both paths, including weighted
mean, min/max, sample count, and user/KST-date aggregates. The private relation
was 1,688,805,376 bytes after the incremental run; the whole measured sequence
increased <code>invites_dw</code> by 1,693,712,384 bytes and cumulative
<code>temp_bytes</code> by 3,735,895,392 bytes. Six detail facts remain empty by
design because no named consumer was approved.

## P6 recovery controls

P6 is the first complete core recovery build. Before it starts:

1. verify all five EL systems completed;
2. run source freshness as a hard gate;
3. record Azure Monitor used and free storage;
4. stop if usage is 80% or higher;
5. record PostgreSQL database size and cumulative
   <code>temp_bytes</code> for comparison;
6. inspect the implemented <code>daily_core</code> selection;
7. run the core with one thread and fail-fast;
8. record pre-run, peak, and post-run storage plus per-node runtime;
9. reconcile dimensions, atomic facts, panels, metrics, PII, and grants;
10. build detail separately only if there is a named need and enough headroom.

A detail failure must not invalidate a successful daily-core run.

Superset refresh happens only after the recovered core passes. Register only
reviewed core/serving relations. Do not bulk-register landing, staging, private
intermediate, or detail relations.

## Operational ownership required before P7

Changmin Ahn is the interim holder of the repository and local environment. That
does not make the local machine a production component. Unattended operation
must not begin until the following responsibilities are assigned in writing.

| Responsibility | Required assignment |
|---|---|
| Scheduler runtime | Approved Azure location plus service identity |
| Daily EL and transform | Named operator who owns failed DAGs and safe reruns |
| Failure notification | Named recipients for source, freshness, storage, and dbt failures |
| Airflow metadata DB | Durable location, backup/restore owner, account and secret rotation |
| Superset runtime and app DB | Runtime owner, backup schedule, tested restore owner |
| <code>SUPERSET_SECRET_KEY</code> | Durable secret-store owner and rotation/recovery procedure |
| Warehouse roles | Credential and grant owner, including <code>superset_reader</code> |
| Azure storage monitoring | Owner for preflight, stop decisions, and capacity trend review |
| Wearable detail | Named access approver and execution owner |
| PII inventory | Owner for target-change review and retention decisions |

P2 verified the real <code>superset_reader</code> login as transaction-read-only,
KST, and <code>marts</code>-only. It read the 487-row search fact while direct
queries against <code>marts_detail</code>, <code>intermediate_private</code>,
<code>staging</code>, and landing were denied. P6 must repeat this check after
the complete core recovery because new relations and defaults can drift.

## Archive policy — resolved 2026-08-21

<code>docs/</code>, <code>data/</code>, and <code>analysis/</code> remain an
ignored, non-authoritative local archive. Historical reasoning under
<code>docs/business_intelligence</code> is preserved without translating or
normalizing its source artifacts. Only durable semantic and evidence rules are
curated into tracked English documents. Archived values, external-study
effects, and scenario outputs are not current warehouse facts. Exact
duplicates, notebook checkpoints, and the superseded autogenerated OLAP plan
were removed; the rest of the ignored archive was left alone.

## Owner decisions and safe defaults

P0 through P4 can proceed without the following semantic decisions. Withhold
the affected public metric until its contract is approved.

| Decision required | Safe default while unresolved |
|---|---|
| First event that qualifies as activation | Store each raw milestone; publish no activation rate |
| Active-event taxonomy and windows for 30/90-day retention | Publish no retention metric |
| Exact business meaning of <code>tb_share_log</code> and <code>point_call_yn</code> | Store a neutral interaction event; do not call it an open or success |
| Whether raw search-term analysis is required | Exclude raw search text at EL |
| Whether external-recipient analysis is required | Do not retain external recipient keys |
| Remote-care qualifying-day definition | Mark as <code>HYPOTHESIS</code>; prohibit revenue or billing claims |
| Device-measurement eligibility denominator | Publish measuring users and reading counts only; do not publish an adherence or participation rate |
| Historical site attribution contract | Prohibit historical attribution until upstream writes preserve old site and real change time |
| Medical and Financial KPI contract | Keep as <code>ROADMAP</code> until encounter/claim sources and grains exist |
| Permanent scheduler and operational owner | Keep automated operation disabled |

The documentation and access review also surfaced these owner contracts:

| Decision required | Safe default while unresolved |
|---|---|
| Small-cell suppression threshold and treatment | Do not publish subgroup metrics that can expose small cohorts |
| Named <code>metric_owner</code> and <code>decision_owner</code> values | Keep the registry in draft and withhold the metric |
| Planning Team access: viewer-only or SQL Lab | Viewer-only; do not claim it is enforced until the role is implemented and tested |
| Analyst audience and database role for <code>marts_detail</code> | Grant nobody general access; approve named analysts individually after P2 |
| Whether withdrawn coaching deliveries belong in the public W-C denominator | Preserve the source state and withhold the adherence metric |
| Monthly high-risk meaning: any-time union, latest/month-end, or two metrics | Keep the states separate and publish neither until named contracts are approved |
| Disposition of the seven legacy PI views and dashboard | Keep them disabled; P5 records keep/replace/retire explicitly |

PII regeneration must also surface these retention decisions:

- whether unused iCHMS auth and membership tables belong in the warehouse;
- the purpose, role access, and retention period for IRS genomic inputs;
- the purpose, role access, and retention period for unused Discovery
  consultation, examination, medical, prescription, genomic, and free-text
  payloads.

Technical choices such as selector syntax, physical heart-rate dedupe,
measurement conflict tests, and current-site column versus current bridge do
not require business approval if they preserve the contracts in
[todo.md](todo.md).

## Known traps

- **Current site is not event-time site.** Current Ulsan/Jeju is a present-day
  filter only.
- **Percentile scores are not additive.** IRS, IRS+, LRS, MRS, and PRS are
  independent 1–100 ranks.
- **Zero can mean unknown.** A stale or not-yet-loaded channel must not become a
  zero-activity observation.
- **Dense panels need reconciliation.** Grain tests alone cannot detect activity
  lost outside the spine.
- **Share has three denominators.** Created links, interacted links, and
  interaction-event rows are different quantities.
- **Share interaction may belong to the recipient side.** Do not count it as a
  sender active-day until its meaning is confirmed.
- **A watermark is not a DAG ledger.** It does not prove an empty incremental
  target ran successfully as part of a complete source run.
- **The PII inventory is a snapshot.** The loader auto-adds upstream columns;
  target changes and added-column logs trigger a new review.
- **The database role is necessary but not sufficient.** EL exclusions, staging
  projections, schema grants, and metric rules are all part of the boundary.
- **Database size is not Azure free space.** Azure Monitor owns the 70% warning
  and 80% stop lines.
- **Superset datasets are single relations.** Site and other temporal semantics
  must be resolved in tested serving relations, not improvised in charts.
- **Historical counts need dates.** Wearable sources backfill, so a count at a
  fixed event cutoff can rise after a later extraction.

## Handover completion definition

Handover is not complete when files exist. It is complete when:

- P0–P6 recovery evidence is recorded;
- the current core graph and Python suite are green;
- current Superset charts return current extraction data;
- the general BI role cannot reach raw detail or PII;
- daily EL → freshness → core transform runs without a local machine;
- the operational owners above are named;
- Airflow metadata and Superset application databases have tested restore
  procedures;
- a successor can diagnose and safely rerun a failure from the English
  operational runbook alone.
