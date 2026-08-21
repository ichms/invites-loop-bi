# Invites Loop BI — Measured Findings and Supersession Ledger

**Last updated:** 2026-08-21 KST

**Status:** historical evidence and design corrections; **not the active implementation plan**

The filename is retained because code comments and migration records cite it. Execution order,
phase gates, stop lines, and completion criteria live only in [`todo.md`](todo.md). If this
ledger conflicts with a current measurement or `todo.md`, it loses.

## 1. Current recovery baseline

The 2026-08-21 baseline replaces every earlier “all phases complete” statement.

| Item | Measured state |
|---|---|
| Extraction targets | 128: iccoli 37, ichms 16, sibc 36, irs 5, discovery 34 |
| Watermarks | 128 rows, all `SUCCESS` |
| Latest new iccoli landing load | approximately 2026-08-21 08:58 KST |
| Warehouse marts | P3 targeted core populated: 81,745 user-days, 2,996 user-months; 6 detail facts remain empty in `marts_detail` |
| Python baseline | offline: 95 passed / 32 skipped after P0; live suite not rerun |
| dbt baseline | historical 388/388 is not a current acceptance result |
| Orchestration | manual only; declared schedules have no operating history |
| Next work | P4: reusable heart-rate dedupe and controlled wearable detail |

No number in this file should be treated as current unless it carries a measurement date.
Wearable counts are especially extraction-date dependent because sources backfill.

## 2. Durable findings

These findings survived the redesign because they were established from source or landing
data and explain current contracts.

### 2.1 Canonical user key

The mart key is the cohort-native `invites_loop.user_id` UUID. iccoli's integer
`user_no` is translated through `tb_ext_user_mapper`, filtered to
`ext_system_code = 'LOOP'`, in dbt staging. A mart must not expose `user_no`.

The mapper is a small membership relation whose upstream deletes matter. An incremental
copy once retained a deleted mapping, so the mapper became a transactional full-refresh
target. Mapper-only and cohort-without-mapper populations must be counted explicitly rather
than disappearing through an inner join.

### 2.2 SiBC daily-log dedupe

Measured on 2026-08-06, `sibc.user_intg_log` and `sibc.user_irs_log` contained genuine
intra-day revisions at `(user_id, ymd)`. `created_at` gave a total ordering in every
duplicate group measured. The staging rule is therefore last-row-wins, followed by a
unique-grain test. `ymd` is source text and is cast to `date` with cast-integrity
testing.

### 2.3 PII was already in landing

The original belief that operational data was already anonymized was false. Direct
identifiers, password hashes, tokens, IP addresses, names, full birth data, free text, and
clinical/genomic payloads had landed in the warehouse.

This established two required boundaries:

- EL must exclude direct identifiers and unnecessary payloads before they leave the source.
- dbt staging must use explicit projections and JSONB allow-lists so prohibited content
  cannot enter marts.

The three newly added search/share targets now implement the same boundary:
filtered full refresh plus source-side exclusion, followed by the reviewed
2026-08-21 landing cleanup. Their raw prohibited fields are no longer present
in the warehouse catalog.

The 2026-08-06 cleanup migrations and matching target exclusions are historical controls,
not proof that future columns are safe. The loader automatically adds upstream columns, so
target changes and “added column” logs require a new PII review. The current snapshot and
open retention decisions are in [`PII_INVENTORY.md`](PII_INVENTORY.md).

### 2.4 Landing, dbt staging, and marts are different layers

The warehouse already used `stg_<system>` for EL landing, so dbt staging models were placed
in a separate `staging` schema. The current mart schema is `marts`. The redesign adds
private reusable physical intermediates and a restricted `marts_detail` schema. P2
implemented those schema/access boundaries and P3 populated the core relations;
P4 implemented and measured the heart-rate physical strategy.

### 2.5 Disease-score source

`fct_user_disease_day` is sourced from the relational `irs.user_irs_hist` data rather
than re-exploding SiBC's `risk_overview` JSON. Measurement showed that the relational
source has the required typed score family and explicit user × day × disease grain.

The user-facing disease catalog and the scoring engine's disease population are not
identical. Reconciliation must preserve source rows while public disease slices apply the
catalog contract explicitly.

### 2.6 Measurement attribution and glucose units

Discovery measurement children identify a lifelog parent, not the user directly. Attribution
must join through `disc_lifelog_user_info`; selecting a user key from a child table is
structurally wrong.

Blood-glucose rows historically arrived in mixed units without a per-row unit. The implemented
heuristic normalizes values below 30 by multiplying by 18.0182 and fails if values enter an
ambiguous guard band. This is a measured fallback, not a substitute for an upstream unit
field. P3 remeasurement retained source transaction, device, platform, and
location because 41 user/time/metric slots repeated and nine differed by platform.

### 2.7 Dense behavioral panels

An activity-only spine produced a biased denominator. `fct_user_day` therefore became a
dense user × day panel, starting at the earlier of enrollment and first observed activity.
Its upper bound is an observation frontier, not `current_date`.

The first reconciliation work caught real activity outside an attempted bounded spine.
`assert_user_day_spine_loses_no_activity` is consequently a structural contract and must
be extended to every new channel. The redesign adds a second distinction: a zero is observed
inactivity only when that channel was eligible and loaded; a stale or not-yet-loaded channel
is unknown.

### 2.8 Wearable grains and duplicate multiplicity

Point samples, intervals, sessions, and daily aggregates have no honest common source grain.
The six source-grain wearable facts remain separate from `fct_measurement` and
`fct_wearable_day`. Exact duplicate payloads collapse to one observation while
`source_row_count` retains delivered-row multiplicity.

This logical finding remains valid. Their physical placement does not: source-grain facts
must move from general `marts` to restricted `marts_detail`, outside `daily_core`.

### 2.9 Current site is not site history

The iCHMS schema can hold multiple user-customer rows, but the application write path has
treated approved deployment site as a scalar. On 2026-08-10, 13 rows were updated in place
from Ulsan to Jeju without changing `linked_dt`; the actual switch time was not stored.

At the 2026-08-21 baseline, the cohort has 437 users and each has exactly one current approved
site: 393 Ulsan and 44 Jeju. This supports a current-state filter only. It cannot attribute a
historical event to the site at which it occurred. A temporal bridge remains blocked on an
upstream unlink/insert and change-time contract.

### 2.10 Search and share signals

Measured at the 2026-08-21 extraction:

| Landing table | Grain key | Rows | Actor users | Observed meaning |
|---|---|---:|---:|---|
| `tb_search_log` | `search_log_no` | 514 | 85 | Search event |
| `tb_share_info` | `share_no` | 1,141 | 151 | Share link/object creation |
| `tb_share_log` | `share_log_no` | 572 | 63 | Neutral downstream interaction candidate |

The actor union is 176 users. Of 1,141 share links, 181 have a downstream log, producing
572 log rows. Link creation count, interacted-link count, and interaction-event count are
three different denominators.

`share_info → share_log` joined completely on `share_no` in the measured snapshot, with
no orphan or sender mismatch. That does not prove `point_call_yn` means open or success.
`share_log` may describe recipient-side activity, so it must not count as sender activity
until the owner confirms the source semantics.

The P0 source recheck at 2026-08-21 11:32 KST measured the physical contract separately
from the 08:58 landing baseline:

| Source table | Declared PK constraint | Unique grain index | Source nullability | Timestamp | All / Loop-filtered rows |
|---|---|---|---|---|---:|
| `tb_search_log` | none | `search_log_no` | all columns `NOT NULL` | `create_datetime timestamptz` | 1,133 / 518 |
| `tb_share_info` | none | `share_no` | all columns `NOT NULL` | `create_datetime timestamptz` | 1,816 / 1,142 |
| `tb_share_log` | none | `share_log_no` | all columns `NOT NULL` | `create_datetime timestamptz` | 1,018 / 573 |

Each unique-indexed grain candidate had zero duplicates. The extractor nevertheless sees
these tables as keyless because it intentionally reads `pg_index.indisprimary`, not an index
name or arbitrary unique index. Both source and warehouse sessions reported `Asia/Seoul`.

`pg_stat_user_tables` reported 14 `tb_search_log` updates, zero `tb_share_info` updates, and
28 `tb_share_log` updates at that recheck. These counters are observations at that timestamp,
not permanent test constants. Because updates do not change `create_datetime`, the three small
tables use filtered full-refresh extraction. `tb_share_info` follows the same policy despite
no observed update because its cost is small and its mutable-write contract is not guaranteed.

The current authoritative documents and DAG header now use the 128-target split
37/16/36/5/34. Superseded references found during recovery were the 123-table inventory,
iccoli 34-target header, and discovery 32-target header; they remain historical evidence only
where explicitly labelled as such.

P1 completed a reviewed small-model build at 2026-08-21 12:28 KST. The exact
selection excluded heart-rate and wearable detail, used one thread and fail-fast,
and finished with 88 passes, zero warnings, and zero errors in 12.79 seconds.
The three source freshness checks passed. Current retained-cohort fact counts are
487 search events, 1,131 share links, and 561 interaction events; 177 retained
share links have an interaction. These are extraction-dated measurements, not
test constants. Dynamic tests reconcile landing → staging → current-cohort facts.

### 2.11 P2 core/detail boundary — implemented 2026-08-21

`daily_core` selects 43 models and excludes all six source-grain wearable facts
plus the two dedicated heavy tests. `wearable_detail` selects the six facts,
their dedicated tests, and only the ancestors needed to execute them.
`scripts/assert_p2_selector_boundaries.sh` makes that graph contract repeatable.

The warehouse migration moved the six empty legacy detail tables from `marts`
to `marts_detail` and moved the populated 47,046-row wearable-day aggregate from
`staging` to `intermediate_private`; it deleted and rebuilt neither. The real
`superset_reader` login read the 487-row core search fact while direct queries
against detail, private intermediate, staging, and landing relations were
denied. dbt parse, selector-specific compile, the graph assertion script, and
the offline Python suite (95 passed, 32 skipped) passed. The complete selectors
were not built: daily core remains gated to P6, and detail remains gated to the
P4 storage-controlled procedure.

### 2.12 The 2026-08-20 storage incident

The operational databases and `invites_dw` share one PostgreSQL endpoint's storage, I/O,
and CPU. Repeated grouping over roughly 9.01 million landing heart-rate rows overlapped with
a full rebuild of roughly 8.88 million detail rows at four threads. That work exhausted the
safe operating envelope and led to the marts being truncated during incident response.

Azure storage was expanded from 128 GB to 256 GB, but capacity expansion did not create
resource isolation. The redesign must calculate heart-rate dedupe once in a reusable physical
relation, apply a bounded lookback/window-replace strategy, and separate daily core from
detail builds. Azure Monitor storage—not only PostgreSQL database size or `temp_bytes`—is
the stop signal.

### 2.13 P3 lifecycle and canonical panels — implemented 2026-08-21

P3 removed current site and every lifetime <code>is_observable_*</code> field
from <code>dim_user</code>. The separate current-site bridge has 437 users
(Ulsan 393, Jeju 44) and an exactly-one-approved-site test. It has no historical
join semantics.

Nine real milestone types produced 2,744 user-milestone rows. Cohort enrollment
preserves its source DATE without fabricating a midnight timestamp; every other
milestone retains a real event timestamp. The versioned cohort registry defines
membership as stable source presence rather than behavior or site.

The measurement fact now has 26,351 rows at user × source transaction × time ×
metric and reconciles the complete value/unit/device/platform/location
signature. Canonical login (53,585 rows), meal (39,701 rows), integrated-analysis,
search/share, coaching, measurement, disease-score, and daily wearable facts
feed the dense panel rather than being re-aggregated from staging.

### 2.14 P4 heart-rate physical path — implemented 2026-08-21

Azure Monitor measured 51.87% storage before the controlled run, 52.43% at the
peak, and 51.86% afterward. A one-thread full build materialized 9,010,144
distinct heart-rate payloads in 68.32 seconds. Their
<code>source_row_count</code> represents 9,010,635 landing rows, retaining 491
exact duplicate rows rather than discarding their analytical weight.

The 30-day window replacement rewrote 1,654,036 payloads in 58.33 seconds. The
landing table has no <code>measured_dt</code> index, so the window reduces group
and rewrite volume but not the 791 MB landing scan. Full-source audits after
both full and incremental paths returned zero differences for source row count,
weighted mean, min/max, sample count, and user/KST-date daily values. The daily
intermediate remained 47,046 rows and the core fact 18,218 rows. No detail fact
was built because no named consumer exists.

The resulting <code>fct_user_day</code> has 81,745 rows and eleven explicit
channel states. Loaded/eligible absence may be zero; stale, not-yet-eligible, or
unknown allocation is NULL with a reason. The 2,996-row monthly panel carries
observed-day denominators, 418 left-partial rows, 437 right-censored rows, and
keeps remote-care qualifying days NULL under
<code>HYPOTHESIS_UNDEFINED</code>. Targeted core tests passed 201/201; P4-only
detail reconciliation remained outside the P3 execution boundary.

## 3. Superseded assumptions and retained reference labels

This section deliberately keeps labels cited by code comments. It records why those
assumptions must not be revived.

### 3.1 “All dbt marts can full-rebuild until runtime exceeds 15 minutes” — superseded

Row count alone was the wrong cost model. Repeated scans, aggregation spill, concurrency,
and shared infrastructure caused failure before an elapsed-time threshold could protect the
system. Materialization is now model-specific. Heart-rate intermediates and detail facts need
bounded incremental/window-replace behavior, while small core models may still rebuild.

### 3.2 “One graph is one safe build unit” — superseded

The old graph coupled small reporting models to source-grain wearable work that had no
canonical metric consumer. The target has independent `daily_core` and
`wearable_detail` selectors plus schema and role separation.

### 3.3 “01:00 EL and 02:00 transform is an orchestration dependency” — superseded

A clock offset proves neither that all five EL pipelines completed nor that their sources are
fresh. Production orchestration must depend on explicit EL completion, hard freshness gates,
and an Azure storage preflight. The current transform DAG implements none of those guarantees
and must stay inactive.

### 3.4 N-01 — EL-boundary minimization — active

Previously classified direct identifiers and unnecessary sensitive payloads are excluded where
configured, not merely hidden in a dashboard. P0 closed the search/share exclusion and landing
cleanup gap. Restoring an excluded field requires an approved purpose, access role, retention
period, and deletion path.

### 3.5 N-02 — Loop cohort filtering — active

Analytical and user-event iccoli tables are filtered in the source query to
actors mapped to `ext_system_code = 'LOOP'`. The deliberately unfiltered
`tb_ext_user_mapper` is the identity bridge that defines and translates this
cohort. The filter is not copied into the loader's staging-window predicate.
Search/share adds both `user_no` and `from_user_no` actor variants.

No manual watermark reset is authorized during P0–P5. A future enrollment-backfill procedure
must be reviewed in the operating runbook rather than inferred from this historical note.

### 3.6 IRS-family residual arithmetic — rejected

IRS, IRS+, LRS, MRS, and PRS are integer ranks from 1 to 100. They are neither additive
components nor residual terms. Subtraction such as
`IRS - (PRS + LRS + MRS)` creates an artifact, not “lifestyle contribution.” Any causal or
component-attribution question belongs to IRS model validation.

### 3.7 Ignored strategy archive — historical provenance, not warehouse evidence

The ignored <code>docs/business_intelligence</code> archive contains useful
historical reasoning, external research, and scenarios, but its self-declared
<code>LOCKED</code>, <code>FROZEN</code>, and <code>SSOT</code> labels are
superseded by the current repository authority order. This warehouse has no
verified GRMC/Guam encounter, admission, claim, billing, revenue, or EBITDA
source. Archived clinical and financial values, old Wellness counts and rates,
and scenario outputs therefore remain non-reproducible historical claims for
this repository.

The 2026-08-21 archive curation promoted only durable rules: metric identity
changes with denominator or population; observations stay separate from
external evidence and scenarios; shared vocabularies do not authorize identity
joins; and W-A/B/C/D are reporting families rather than a causal chain. Exact
duplicates, notebook checkpoints, and a superseded autogenerated architecture
plan were removed. No tracked artifact depends on an ignored archive path.

## 4. Historical delivery record

The repository previously produced a tested dbt star, metric views, and a local Superset
dashboard. Historical runs such as 388/388 dbt nodes and 125/125 Python tests demonstrate
that the earlier implementation once executed; they do not validate the current landing
snapshot, the empty marts, or the redesigned graph.

The following earlier implementation choices remain only as migration input:

- six raw wearable facts in `marts`;
- lifetime `is_observable_*` flags in `dim_user` and the wide panel;
- current site named ambiguously as `site_id`;
- seven `v_pi_*` views without a registry, evidence status, censoring, or `data_as_of`;
- a transform DAG that ignores freshness failure, runs a bare full build, and retries it;
- a Superset registration script that registers every relation in `marts`.

P2–P5 explicitly keep, replace, move, or retire these artifacts. Until P6 validates the new
graph, none of them is a quotable production surface.

## 5. What this ledger does not decide

Owner-facing semantic decisions—activation, retention windows, share meaning, search-term
retention, external recipients, remote-care qualification, measurement eligibility,
historical site, Medical/Financial KPI contracts, and operations ownership—are centralized
in [`HANDOVER.md`](HANDOVER.md). Their safe defaults are to withhold the affected public
metric or data.

Technical execution remains the P0–P7 sequence in [`todo.md`](todo.md).
