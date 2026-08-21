# metrics — versioned public metric contracts

Metric views are thin, reviewable relations over canonical marts. The SQL view,
its registry row, tests, and ownership fields together define a metric. A chart
calculation or dashboard label does not.

## Current state — 2026-08-21

The current `v_pi_*` views are a legacy baseline, not the completed W-A/B/C/D
semantic layer. P3 populated canonical facts and panels, but these views have
not passed metric-level acceptance and must not be interpreted as public
results. The repository does not yet contain:

- a metric registry;
- evidence-status or `data_as_of` fields on public metrics;
- non-empty and fresh-period tests that fail when a metric silently returns no
  data.

P5 must record whether each existing view is kept, replaced, or retired. Do not
call the legacy views canonical or publish their current results. The
implementation contract is [`todo.md`](../../../../todo.md).

## Registry contract

Before a public view name is finalised, add it to
`dbt/seeds/metric_registry.csv` or an equivalent git-tracked contract. Each
metric requires at least:

- `metric_id`, `metric_version`, and a meaning-based name;
- `metric_tier`, `evidence_status`, and evidence provenance;
- population or deployment scope, entity, and grain;
- aggregation, numerator, denominator, and eligibility;
- time alignment, timezone, and censoring rule;
- source frontier and `data_as_of`;
- assumption version for a derived model, hypothesis, scenario, forecast, or
  valuation;
- small-cell rule; and
- metric owner and decision owner.

Do not encode a changeable presentation order such as `kpi_1` in a model or
metric ID. A change to population, denominator, eligibility, grain, or time
alignment requires a new semantic version or metric ID.

## Evidence status

| Status | Meaning | Reporting rule |
|---|---|---|
| `OBSERVED` | Directly counted from a source event or state with a tested grain | Report with denominator and freshness context |
| `DERIVED` | Computed from observed data under an explicit transformation | State the derivation and validation limits |
| `HYPOTHESIS` | Plausible analytical signal whose interpretation is not validated | Never present as an outcome or causal effect |
| `ROADMAP` | Required source or semantic contract does not exist | Show the gap, not a fabricated number |

Evidence status is independent of whether a business label says KPI or PI. A
Wellness signal does not become a Medical outcome because it is shown beside
one on a dashboard.

External literature may support a hypothesis or pilot design, but does not
upgrade a local warehouse metric's evidence status. A simulation, forecast, or
valuation is never `OBSERVED`, even if all its inputs are observed; keep its
assumptions, owner, provenance, range, and sensitivity explicit.

## Target metric families

Exact IDs and view names are chosen only after their registry contracts are
approved. These families organize reporting questions; they are not a MECE
population partition or a proven causal funnel.

| Family | Target contract |
|---|---|
| W-A — acquisition and activation | A same-population funnel over source-backed registration, enrolment, and activation milestones |
| W-B — engagement and retention | Active-user depth and cohort-relative 30/90-day retention under one versioned event taxonomy and explicit censoring |
| W-C — coaching behaviour | Delivered, responded, and completed events kept distinct; event-weighted and user-weighted metrics are separate |
| W-D — risk movement | Representative user × disease × period ranks aggregated with explicit user weighting and scoring coverage |
| Measurement | Measuring users and readings; no participation rate without a device-eligibility denominator |
| Remote-care readiness | `HYPOTHESIS` until a qualifying-day contract exists; never a billing or revenue metric |
| Behaviour-to-risk bridge | Explicit exposure and outcome windows, minimum sample rule, and non-causal language |
| Medical and Financial | `ROADMAP` when encounter, admission, claim, or billing sources are absent |

## View design rules

1. One view represents one metric contract. Supporting numerator, denominator,
   eligible population, and sample-size columns belong beside the result so it
   can be audited.
2. Numerator and denominator must use the same entity, time alignment, and
   eligibility rules.
3. A zero is reportable only when the source channel was eligible and loaded.
   Unknown coverage must not be rendered as zero.
4. Every public result provides `data_as_of` or joins to one documented
   freshness relation.
5. IRS, IRS+, LRS, MRS, and PRS are 1–100 ranks. Do not add, subtract, or call
   their movement a clinical effect.
6. Current site is a present-state filter only. It cannot attribute an older
   metric period to an event-time site.
7. A monthly high-risk union and a month-end/latest high-risk state are
   different metrics and must have different contracts.
8. A cohort-relative curve must expose right-censoring. Thirty-day and 90-day
   retention cannot share a denominator merely to fit one chart.
9. Small-cell suppression is applied before a public chart can reveal a
   sensitive subgroup.
10. Metric SQL stays thin. High-cost deduplication and canonical aggregation
    belong upstream in tested physical models.
11. A shared schema, field name, or FHIR/USCDI label does not establish a
    shared population or identity join. Cross-deployment joins require a
    source-backed identity map, compatible as-of contract, and row-loss
    reconciliation.

## Legacy view review

P5 must make the disposition explicit. The current risks are:

| Legacy view | Required review |
|---|---|
| `v_pi_app_engagement_daily` | It counts app-action users only; it is not the future login/action/search/share active-event taxonomy |
| `v_pi_coaching_adherence_daily` | It is event-weighted and treats withdrawn deliveries as denominator events; delivered/responded/completed semantics need approval |
| `v_pi_coaching_adherence_by_domain` | It has no period axis or user count and is event-weighted only |
| `v_pi_measurement_participation_weekly` | Counts users and readings but has no device-eligibility denominator; do not call it a rate |
| `v_pi_population_risk_monthly` | Averages disease-day rows directly instead of representative user × disease × period values |
| `v_pi_high_risk_disease_load_monthly` | Uses a month-any union that must not be confused with latest or month-end risk |
| `v_pi_scoring_coverage_monthly` | Uses the current total cohort as every historical denominator rather than period eligibility |
| `v_bridge_pi_to_kpi` | Keep as a gap register, but migrate it to evidence status and avoid treating a proxy as the missing outcome |

## Testing requirements

Column `not_null`, `unique`, and range tests pass vacuously on an empty view.
They are necessary but insufficient. Each public metric also needs tests for:

- declared grain;
- numerator not exceeding denominator where applicable;
- eligibility and censoring reconciliation;
- a non-empty expected period;
- a fresh expected period and valid `data_as_of`;
- allowed evidence status and registry/view consistency; and
- small-cell handling where subgroup rows are exposed.

Metric tests do not replace the grain, FK, PII, and reconciliation tests on the
canonical facts beneath them.

## Safe development and release

P1–P5 allow only exact, reviewed small-model builds. First inspect the exact
selected graph. Use one thread and fail-fast, avoid unreviewed `+` expansion,
and stop if the selection reaches heart-rate or wearable detail. A
directory-wide `--select metrics` command is not an approved substitute for
graph review.

The first complete release is P6, after the metric registry and core/detail
selectors exist. Required source freshness is a hard gate, Azure Monitor
storage must be below the stop line, and `daily_core` must be green before any
dataset or dashboard update.

There is no automatic 02:00 build today. EL and dbt remain manual, and the
existing transform DAG must not be enabled until P7 replaces fixed-time
assumptions, ignored freshness failures, and blind full-build retry.

For analyst-facing interpretation, see the
[Superset metric guide](../../../../deploy/superset/METRICS.md). For core model
boundaries, see the [marts guide](../README.md).
