# Superset metric interpretation guide

This guide explains how to read public Invites Loop metrics. Approved public
metric definitions will live in Git-tracked dbt views and a versioned registry;
Superset will present those contracts but will not define them.

## Current state — 2026-08-21

There are no accepted public dashboard results. P3 targeted builds populated
canonical core relations, but the W-A/B/C/D registry and semantic layer are not
implemented and Superset was not refreshed or smoke-tested. The existing PI
dashboard and its legacy views must not be used for operating decisions.

Public release resumes in P6 only after the registry, canonical facts and
panels, core/detail access boundary, freshness gate, Azure storage gate, dbt
tests, and Superset reader checks pass. The implementation contract is
[`todo.md`](../../todo.md).

## What defines a metric

A public metric consists of four reviewed artifacts:

1. a registry row that states meaning, grain, evidence, denominator,
   eligibility, time alignment, censoring, freshness, small-cell handling, and
   ownership;
2. one thin dbt view that implements that contract;
3. tests that prove grain, denominator, freshness, non-empty expected periods,
   and reconciliation; and
4. a Superset dataset and chart that display the result without redefining it.

Changing a chart label or adding a dashboard calculation does not change the
metric. Semantic changes go through the registry and SQL in git review.

## Evidence labels

Every public chart must display or make directly available one of these labels:

| Evidence status | Meaning | Safe interpretation |
|---|---|---|
| `OBSERVED` | Direct source event or state under a tested grain | “The system recorded this.” |
| `DERIVED` | Calculation from observed inputs under a documented method | “This modelled value moved under the stated definition.” |
| `HYPOTHESIS` | Unvalidated signal or proposed analytical bridge | “This is worth investigating,” not “this caused an outcome.” |
| `ROADMAP` | Required source or semantic contract is missing | No number should be shown. Display the gap instead. |

KPI, PI, and Bridge labels may still describe business roles, but they do not
override evidence status. An observed app event is not a Medical outcome, and a
hypothesised bridge is not causal evidence.

### Separate observations, external evidence, and scenarios

Only a direct, tested local source event or state can be <code>OBSERVED</code>.
External literature may justify a <code>HYPOTHESIS</code> or pilot design; it
does not turn a local association into an outcome or causal effect. When cited,
record the study design and population, full intervention and comparator,
endpoint and follow-up window, baseline rate, effect measure and uncertainty,
verification status, transportability limits, and material null or contrary
evidence.

A simulation, forecast, or valuation is a separate evidence object from its
inputs. It must retain <code>DERIVED</code> or <code>HYPOTHESIS</code> status and
show its assumption version, owner, provenance, and range or sensitivity. An
observed input never makes a scenario output observed.

## Target Wellness families

Exact metric IDs and view names are not final until the registry is approved.
The W-A/B/C/D families organize questions; they are not a MECE population
partition or a proven causal funnel.

| Family | What it may report | Mandatory qualification |
|---|---|---|
| W-A — acquisition and activation | Source-backed registration, enrolment, and activation milestones | One population through the funnel; activation event owner-approved |
| W-B — engagement and retention | Active users, depth, and cohort-relative 30/90-day retention | Versioned active-event taxonomy, eligibility, and right-censoring |
| W-C — coaching behaviour | Delivered, responded, completed, latency, and adherence | Event-weighted and user-weighted results separated; denominator visible |
| W-D — risk movement | Scoring coverage and user-disease-period rank trajectories | Representative period value, user weighting, and no clinical-effect language |
| Measurement | Measuring users and readings | No participation rate without a device-eligibility denominator |
| Remote-care readiness | Qualifying days under an approved definition | `HYPOTHESIS`; never revenue, billing, or reimbursement |
| Medical and Financial | Admission, LOS, readmission, claim, or billing outcomes | `ROADMAP` until real source grains exist |

## Reading rules

### Check evidence and freshness first

Read `evidence_status` and `data_as_of` before reading the value. The dashboard
must also show the last successful EL and core-build timestamps. A stale chart
is not a fresh zero.

### Inspect the denominator and eligibility

A percentage without its denominator is not auditable. The metric relation must
carry the numerator, denominator, eligible population, and relevant sample
counts. Device measurement counts do not become an adherence rate when device
allocation is unknown.

### Distinguish observed zero from unknown

A dense user-day or user-month panel can contain real zero-activity periods,
but only for a channel known to be eligible and loaded. A channel that is stale,
not yet loaded, or ineligible is unknown and must not render as zero.

### Respect time alignment and censoring

Calendar months and months since enrolment answer different questions.
Cohort-relative retention excludes people who have not yet had enough follow-up
time. A 30-day and a 90-day curve cannot silently use the same denominator.

Changing the population, denominator, eligibility rule, grain, or time
alignment changes the metric definition. Assign a new semantic version or
metric ID rather than preserving the old ID behind a new chart label.

### Do not infer a shared population from a shared schema

A common field name, dimension vocabulary, or FHIR/USCDI resource label does
not prove that two datasets describe the same people or can be joined. A
cross-deployment join needs a source-backed identity map, compatible as-of
contract, and row-loss reconciliation. Without all three, keep the populations
and their metrics separate.

### Treat IRS-family values as ranks

IRS, IRS+, LRS, MRS, and PRS are 1–100 ranks. They are neither absolute clinical
risk nor additive components. Do not sum them, subtract one from another, infer
a residual, or claim that rank movement proves a clinical outcome.

For disease metrics, keep the user-facing catalogue boundary explicit. A
monthly union of diseases that were ever high-risk is different from the latest
or month-end state; the chart and registry must say which one it uses.

### Do not backfill historical site from current site

The approved Ulsan/Jeju mapping is current state only. Known in-place source
updates erased previous site values and actual switch times. A current-site
filter may describe today's population; it cannot attribute an older event to
the site where it happened.

### Separate active and passive signals

Login, app action, search, share creation, coaching, manual measurement, meal,
and passive wearable collection are different channels. Do not add them into a
single “engagement” number without a registry contract. `tb_share_log` remains
a neutral interaction event until its business meaning is confirmed and does
not make the sender active by default.

### Attach an extraction date to wearable counts

Wearable sources backfill for roughly 30 days, so a count for a fixed event-date
cutoff can rise after later extractions. Quote the extraction date with every
wearable count.

### Avoid causal language

Engagement, adherence, measurement, and IRS movement can be associated. They do
not prove that one caused another or that a Medical or Financial outcome
improved. A behaviour-to-risk bridge needs explicit exposure and outcome
windows, a minimum-sample rule, and `HYPOTHESIS` or `DERIVED` status as
appropriate.

### Apply small-cell rules

Site, disease, cohort, and intersection filters can create sensitive small
groups. A chart must follow the registry's suppression or aggregation rule
before it is public. No default threshold has been approved yet, so affected
metrics remain unpublished until that owner decision exists.

## Legacy views are not the target contract

P5 must keep, replace, or retire each legacy view. Their current names do not
make them safe definitions:

| Legacy view | Why it cannot be treated as the final public metric |
|---|---|
| `v_pi_app_engagement_daily` | Counts app-action users only, not the future versioned active-event taxonomy |
| `v_pi_coaching_adherence_daily` | Event-weighted only; withdrawn-delivery and response semantics are not owner-approved |
| `v_pi_coaching_adherence_by_domain` | Has no period or user denominator |
| `v_pi_measurement_participation_weekly` | Has measuring users/readings but no device-eligibility denominator |
| `v_pi_population_risk_monthly` | Directly averages disease-day rows rather than representative user-period values |
| `v_pi_high_risk_disease_load_monthly` | Month-any union can be mistaken for latest or month-end state |
| `v_pi_scoring_coverage_monthly` | Uses the current cohort as each historical denominator |
| `v_bridge_pi_to_kpi` | Useful as a gap register only; its proxies are not the missing outcomes |

The current dashboard chart inventory mirrors these legacy views and is also
under review. It must not be rebuilt until P5 disposition and the P6 core build
are complete.

## Missing Medical and Financial outcomes

The warehouse has no verified admission, discharge, LOS, readmission, claim,
billing, or revenue fact. Do not create views that return zero or null and do
not relabel Wellness signals as substitutes. Record each missing source and
grain as a `ROADMAP` gap in the bridge register.

When a source arrives, source grain, population, time alignment, eligibility,
reconciliation, and evidence status must be validated before a number becomes
public.

## Requesting or changing a metric

A request must answer:

- What decision will this metric support?
- What population or deployment does it describe?
- What is the entity and grain?
- Which source event or state is observed?
- What are the numerator, denominator, and eligibility rules?
- How are time alignment and censoring handled?
- What is the evidence status?
- What is the evidence provenance and, for a model or scenario, assumption version?
- What is the source frontier and `data_as_of` rule?
- What small-cell rule applies?
- Who owns the metric meaning and who owns the decision?

If those questions are unresolved, the safe result is a registry draft or a
`ROADMAP` gap, not dashboard SQL. Developer implementation and release gates
are documented in the
[dbt metric guide](../../dbt/models/marts/metrics/README.md).

## Access governance

The warehouse connection is read-only and is intended to expose core `marts`
relations only. Source-grain wearable data belongs in `marts_detail` and must
remain unavailable to the general Superset role.

The repository does not currently create or verify a Planning Team application
role or prove that SQL Lab is disabled. Do not rely on that old claim. P6 must
verify database access boundaries, and any viewer/editor policy must be created
and tested explicitly in Superset.
