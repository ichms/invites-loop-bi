# marts — core serving models

The target mart is a Wellness-first analytical core built from conformed
dimensions, atomic facts, sparse daily intensity facts, and dense user-period
panels. Metric views are thin serving contracts over that core.

## Current state — 2026-08-21

P3 targeted builds restored the redesigned dimensions and atomic facts plus
2,744 lifecycle milestones, 81,745 user-days, and 2,996 user-months. Lifetime
`is_observable_*` fields are gone, current site is isolated in
`bridge_user_site_current`, and channel completeness/eligibility is explicit.
P2's selector/schema/access boundary remains in force. The graph still has no
P4 reusable heart-rate dedupe or P5 metric registry, and the complete
`daily_core` recovery remains gated to P6.

Do not present the target structure as deployed, run a bare full build, enable
the transform DAG, or register all current marts relations in Superset. The
implementation order and completion gates are in [`todo.md`](../../../todo.md).

## Target schema boundary

| Schema | Contents | Intended access |
|---|---|---|
| `marts` | Conformed dimensions, atomic core facts, `fct_wearable_day`, dense panels, serving relations, and thin metric views | General BI and `superset_reader` |
| `marts_detail` | Six source-grain wearable observation facts | Explicit analyst role only |
| `intermediate_private` | Reusable high-cost deduplication and aggregation relations | dbt execution role only |

Landing, dbt staging, physical intermediates, and `marts_detail` must remain
unavailable to the general Superset role. P2 verified these denials through the
actual `superset_reader` login; P6 repeats the check after core recovery.

## Non-negotiable modelling rules

1. Every fact declares its grain in the SQL header and enforces that grain with
   an appropriate uniqueness test.
2. `fct_user_day` remains a dense panel. Zero-activity days are part of the
   denominator when the relevant channel is known to be observable and loaded.
3. A stale, ineligible, or not-yet-loaded channel is unknown, not zero.
4. Panel upper bounds use observed source frontiers, never `current_date`.
5. A real event before enrolment extends the user's lower bound; it must not be
   dropped to force non-negative relative time.
6. Source user serials never appear in a mart. `user_id` is the only user key
   exposed here.
7. Direct identifiers, free text, access tokens, device fingerprints, and
   unnecessary external keys never enter a general mart.
8. Current site is a present-state filter only. It must never be joined to a
   historical event as the site at which that event occurred.
9. IRS, IRS+, LRS, MRS, and PRS are 1–100 ranks. They are not additive
   components, and no residual may be derived from them.
10. Numerator, denominator, eligibility, censoring, source frontier, and
    `data_as_of` must be inspectable together for every public metric.
11. Source-shaped events remain separate atomic facts. Similar-looking rows
    from different systems are not cross-source deduplicated for convenience.
12. Raw wearable detail is never part of an ordinary daily-core build.

## Target model families

| Family | Target treatment |
|---|---|
| Stable dimensions | Keep `dim_date`, `dim_disease`, `dim_action`, `dim_device_type`, and `dim_deployment_site` |
| `dim_user` | One row per user; identity, enrolment, and current profile only |
| Current site | `bridge_user_site_current.current_site_id`; no historical meaning |
| Lifecycle | `fct_user_milestone` from real source dates/timestamps only |
| App events | Keep `fct_app_action`; add atomic search, share-link, and neutral share-interaction facts |
| Coaching and measurement | Atomic facts; measurement preserves source transaction/device/platform/location |
| Risk | Keep `fct_user_disease_day` and state that it contains derived rank outputs |
| Wearables | Keep sparse `fct_wearable_day` in core; move six observation facts to `marts_detail` |
| Dense panels | `fct_user_day` from canonical facts plus `fct_user_month` with censoring |
| Superset serving | `fct_user_day_wide` contains no lifetime future-information fields |
| Metrics | Keep, replace, or retire existing views under a versioned metric registry |

## Dense user-day and user-month panels

`fct_user_day` is not a log of things that happened. It is one row per user and
day from the earlier of enrolment and first observed activity through the
measured observation frontier, including eligible days with no activity.

The zero days are essential denominators, but only after load coverage is
known. A recent zero from a stale source is a pipeline state masquerading as
behaviour. The redesigned panel carries channel-specific completeness,
frontier, and eligibility state so a consumer can distinguish:

- observed activity;
- observed zero activity; and
- unknown because the channel was stale, ineligible, or not loaded.

Login, app action, search, share creation, coaching, measurement, meal, routine,
and wearable channels must remain explicit. A share interaction does not count
as a sender active-day until its source meaning is confirmed.

[`assert_user_day_spine_loses_no_activity.sql`](../../tests/assert_user_day_spine_loses_no_activity.sql)
is the reconciliation tripwire for bounded spines. It must be extended to every
canonical channel rather than removed. Per-channel atomic-fact totals and panel
totals must agree.

`fct_user_month` provides both calendar and cohort-relative months. It must
carry denominator pairs, partial-period flags, and right-censoring state rather
than forcing every consumer to reconstruct them.

## Dimensions, milestones, and future leakage

`dim_user` is SCD Type 1 and must contain only stable or explicitly current
attributes. Lifetime behaviour-derived fields such as `is_observable_*` and
`is_observable_wearable_and_routine` leak future outcomes into earlier rows and
are deliberately absent.

Lifecycle observations belong in `fct_user_milestone` at
`user_id × milestone`. Date-only enrollment preserves DATE precision with no
fabricated timestamp; other rows require real source timestamps. Do not
manufacture placeholder dates for stages the sources cannot observe.

The current approved Ulsan/Jeju relationship is a current-state filter. Known
in-place source updates erased the prior site and actual switch time, so
`bridge_user_site_current` cannot support historical or as-of site attribution.

## Wearable core and detail

`fct_wearable_day` remains sparse: a row means at least one wearable stream
fired for that user-day. A null measure on a present row means that particular
stream did not fire; it is not a physiological zero. Exact duplicate source
payload multiplicity must remain available through `source_row_count`, and
daily sample counts and averages must preserve that multiplicity.

The six source-grain facts belong in `marts_detail` for monitored
observation-level analysis. They are not general Superset datasets and are not
dependencies of `daily_core`. Any detail build requires Azure storage
monitoring, one thread, fail-fast, and the stop procedure in `todo.md`.

Wearable counts backfill for roughly 30 days. Quote a count only with its
extraction date.

## Metric layer

Metric views live under [`metrics/`](metrics/README.md). One public relation
represents one reviewable metric contract. The contract is defined in git and
must include evidence status, denominator, eligibility, time alignment,
censoring, freshness, and ownership. A dashboard expression is not the source
of truth.

No admission, LOS, readmission, claim, billing, or revenue metric may be
fabricated from Wellness activity. Those gaps remain `ROADMAP` entries in the
bridge register until a real source and grain exist.

## Build and access gates

P1–P5 use exact, reviewed small-model selections only. Inspect the selected
graph before mutation, use one thread and fail-fast, and reject a selection that
reaches raw heart-rate or wearable detail.

After P2 creates selectors, graph inspection is read-only:

```bash
uv run dbt ls --project-dir dbt --selector daily_core
uv run dbt ls --project-dir dbt --selector wearable_detail
```

The first complete `daily_core` build belongs to P6 and requires:

- all five EL paths successfully completed;
- required source freshness passing as a hard gate;
- Azure Monitor storage checked immediately before execution and below the 80%
  stop line;
- `daily_core` proven not to select source-grain wearable facts;
- one thread and fail-fast; and
- grain, FK, PII, panel, risk, and wearable reconciliation tests in the graph.

Only after the core is green may Superset datasets be registered against the
new core relations. `superset_reader` must then be tested to prove that it
cannot read landing, staging, physical intermediates, or `marts_detail`.
