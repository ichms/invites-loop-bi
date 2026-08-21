# Invites Loop BI — Architecture Decision Log

**Version:** 1.0

**Last updated:** 2026-08-21 KST

**Scope:** ELT, warehouse semantics, BI access, and safe operation

This log records durable decisions and their rationale. It is not an execution plan.
[`todo.md`](todo.md) is the current authority for sequencing, gates, and completion.
Measured source or landing facts override both documents when they conflict.

## 1. Governing principles

1. **A number is publishable only when its grain, population, denominator, eligibility,
   censoring, freshness, and evidence status are explicit.**
2. **Loud failure beats plausible wrong output.** Grain, reconciliation, freshness, drift,
   and non-empty checks are product controls.
3. **Observed data and strategic intent are different things.** The W → M1 → M2 → M3 → W
   strategy is useful context, but the present estate has Wellness data and no verified
   admission, discharge, claim, billing, or RCM fact.
4. **Shared infrastructure is a production constraint.** The operational databases and
   warehouse share PostgreSQL storage, I/O, and CPU. Query cost is part of correctness.
5. **Current state and historical state must not be conflated.** This applies especially to
   site, eligibility, lifecycle milestones, and source freshness.
6. **The repository must be operable without its original author.** Decisions belong in
   Git, and a local laptop is never a production dependency.

## 2. Architecture

### Current state

```text
sources
  → stg_<system> landing
  → staging views / intermediate_private daily wearable table
  → marts (P3 dimensions, atomic facts, lifecycle, daily/month panels)
      + unaccepted legacy metric views
  → marts_detail (6 empty source-grain wearable facts)
  → local Superset (not refreshed or accepted against P3)
```

P2 separated the graph and database access with `daily_core` and
`wearable_detail` selectors, `intermediate_private`, and `marts_detail`. P3
implemented the core lifecycle and panels through reviewed targeted builds.
The graph still has no metric registry or reusable heart-rate dedupe, and the
complete `daily_core` recovery remains gated to P6.

### Approved target

```text
operational PostgreSQL sources
  ↓  COPY-based EL with source-side minimization and cohort filters
stg_<system> landing
  ↓  cast, dedupe, key translation, explicit projection, JSONB allow-list
staging
  ↓
private reusable physical intermediates
  ├─ daily/core transformations
  │    ↓
  │  marts
  │    ├─ conformed dimensions
  │    ├─ atomic event facts
  │    ├─ dense user-day and user-month panels
  │    └─ thin, registry-backed metric views
  │         ↓
  │       Superset via a marts-only read role
  │
  └─ source-grain wearable transformations
       ↓
     marts_detail
       └─ named analyst role only; never general Superset
```

## 3. Active and target decisions

Status has operational meaning:

- **Active** means the rule is implemented or directly enforceable in the
  current repository.
- **Active with disclosure** means the current implementation is valid only
  when its stated interpretive limitation travels with it.
- **Approved target** means the decision is binding but its named todo phase
  has not implemented or verified it yet.
- **Incomplete control** means only part of the required boundary exists.
- **Deferred** means no implementation is authorized until its prerequisite or
  owner decision exists.

### 3.1 Transformation and data contracts

| ID | Status | Decision and rationale |
|---|---|---|
| D-01 | Active | **Use dbt Core for transformation.** SQL, tests, lineage, and review stay in Git. |
| D-02 | Approved target | **Production transform starts only after explicit completion of all five EL pipelines, hard source-freshness checks, and an Azure storage preflight.** A 01:00/02:00 clock offset is not a dependency. P7 implements the dependency and gate; the production command is the `daily_core` selector with one thread and fail-fast, with no blind full-build retry. |
| D-03 | Active | **Stay on pinned dbt Core, not a second transformation runtime.** Fewer runtimes reduce handover and failure surface. |
| D-04 | Active | **Every fact declares its grain in the SQL header and has a matching uniqueness test.** The exact test may be a compound-grain test or a unique observation identifier. |
| D-05 | Active | **Extracted JSONB fields have explicit nullability/drift contracts.** Unknown payload keys fail the allow-list drift check; null-rate thresholds are measured and reviewed, not raised to silence a failure. |
| D-06 | Active | **Use conformed dimensions and source-appropriate facts.** The purpose is falsifiable grain and legal joins, not textbook ceremony. |
| D-07 | Active | **Use the existing `user_id` UUID as the conformed user key.** Translate iccoli `user_no` once in staging; do not mint a third synthetic identity. |
| D-08 | Active | **Dimensions hold stable or explicitly current SCD1 attributes only.** Lifecycle and behavior belong in event facts; history requires a source-supported event or tested temporal bridge. P3 removed lifetime behavior fields and separated current site. |
| D-09 | Active | **Avoid speculative snowflakes and compound cohort tables.** Reusable named cohorts are versioned predicates over stable dimensions and event-time relations. |
| D-10 | Approved target | **Each public metric has one thin view backed by a Git-tracked registry.** P5 creates the registry; a prefix alone is not governance. The contract includes evidence and provenance, population scope, entity, grain, aggregation, numerator, denominator, eligibility, time alignment, censoring, timezone, frontier, `data_as_of`, small-cell rule, assumption version where applicable, and owners. |

### 3.2 BI and deployment

| ID | Status | Decision and rationale |
|---|---|---|
| D-11 | Active | **Apache Superset remains the general BI viewer.** It is a presentation and exploration layer, not the semantic source of truth. |
| D-12 | Active | **Do not build a custom KPI frontend.** The expensive logic belongs in tested warehouse relations. |
| D-13 | Active | **Superset's application database is PostgreSQL.** It is distinct from the data warehouse and must have durable backup and restore ownership. |
| D-14 | Active | **Pin the Superset image and dependencies.** No `:latest`; upgrades require a backup and migration review. |
| D-15 | Incomplete control | **Backups count only after a restore drill.** The application DB, `SUPERSET_SECRET_KEY`, and stored credential recovery must be tested together. |
| D-16 | Active | **General BI access is database-enforced and limited to core `marts`.** P2 moved six detail facts to `marts_detail`, moved the reusable daily aggregate to `intermediate_private`, denied landing/staging/private/detail access, and verified those denials through the real Superset database login. EL exclusion and dbt projection remain separate PII controls. |
| D-17 | Approved target | **Planning users are viewer-only; SQL Lab is for explicitly authorized analysts.** The repository does not yet provision or verify that Superset application role, so documents must not claim the control is live. |
| D-18 | Active | **Reporting sessions use `Asia/Seoul`.** KST is a data-correctness rule for business dates and `timestamptz` grouping. |
| D-19 | Approved target | **Canonical dashboard content may be generated from code only after P6 validates the semantic layer.** Legacy dashboards are not current evidence. |
| D-20 | Active | **Keep the deployment image minimal.** Add only required database drivers to the pinned upstream image. |
| D-21 | Deferred | **No production Superset hosting platform is selected.** Platform choice does not block mart correctness. |
| D-28 | Incomplete control | **Local Superset is a development tool, never an operating component.** The local boundary is explicit, but production still needs a service identity, durable metadata DB, backups, alerts, and a named owner. |

### 3.3 Privacy and identity

| ID | Status | Decision and rationale |
|---|---|---|
| D-22 | Active | **Direct identifiers, credentials, tokens, unnecessary external keys, and unapproved free text must be excluded at EL and absent from dbt outputs.** P0 applied the complete search/share exclusions and removed the previously landed prohibited columns. Transform-only hiding remains insufficient because landing and backups are exposure surfaces. |
| D-23 | Active | **Where age analysis is approved, retain only the minimum useful birth representation.** SiBC and iCHMS full birth values are excluded at EL. The approved iccoli raw birth value remains restricted to landing and is reduced to birth year before dbt outputs and general marts. |
| D-24 | Active with disclosure | **Event-time age uses one documented mid-year birth-year convention.** It is an approximation and is unsuitable for narrow age thresholds. |
| D-25 | Active | **Do not store a static age in `dim_user`.** Age is event-time or serving-layer derivation. |
| D-26 | Active | **JSONB extraction uses an allow-list.** Unknown keys are denied by default. |
| D-27 | Active | **Pair the allow-list with schema-drift detection.** Silent payload growth is unacceptable. |

### 3.4 Panels, wearable data, lifecycle, and site

| ID | Status | Decision and rationale |
|---|---|---|
| D-29 | Active | **`fct_user_day` is a dense user × day behavioral panel.** Zero days are required denominators, and the spine begins at the earlier of enrollment and first activity. |
| D-30 | Active | **Panel bounds and zero semantics are channel-aware.** The upper bound is an observed/load frontier; stale, ineligible, or not-yet-loaded channels are unknown, not zero. Current watermarks provide `TARGET_SUCCESS_ONLY`, not DAG completion. |
| D-31 | Active, P4 incomplete | **Source-grain wearable facts remain separate by honest grain in `marts_detail`.** P2 established the selector/schema/access boundary; P4 must still implement the measured incremental detail path. Daily reporting uses `fct_wearable_day`, and exact duplicates retain `source_row_count`. |
| D-32 | Active with disclosure | **Deployment site is current-state only.** `bridge_user_site_current.current_site_id` is a current filter. Never attach it to historical facts as event-time site. |
| D-33 | Active | **Lifecycle is modeled as atomic milestones.** `fct_user_milestone` stores only real source dates/timestamps; date-only enrollment does not gain a fabricated midnight timestamp and missing stages have no placeholder rows. |
| D-34 | Active | **Search, share-link creation, and share interaction are separate atomic facts at their measured source unique-index grains.** The source tables have no declared PK constraints; the indexed identifiers are currently unique and tested. The facts are not merged with one another or convenience-deduped against `fct_app_action`. |
| D-35 | Approved target | **Heart-rate payload dedupe is computed once in a reusable physical relation.** Daily aggregate, detail fact, attribution, and reconciliation consume the same relation; multiplicity-weighted results must match the prior definition. |
| D-36 | Active, execution pending | **`daily_core` and `wearable_detail` are independent selectors and operating units.** P2 graph assertions prove the boundary. Complete core execution waits for P6 and measured detail execution waits for P4; a detail failure cannot invalidate the last successful core build. |

### 3.5 Semantic layer

| ID | Status | Decision and rationale |
|---|---|---|
| D-37 | Approved target | **The near-term semantic layer is Wellness-first: W-A acquisition/activation, W-B engagement/retention, W-C behavior execution, and W-D risk-score movement.** These are reporting question families, not a MECE population partition or a proven causal value chain. Each transition needs source-backed milestones and its own denominator. |
| D-38 | Approved target | **Evidence status is visible:** `OBSERVED`, `DERIVED`, `HYPOTHESIS`, or `ROADMAP`. A derived rank movement is not a clinical effect. External literature can support a hypothesis or pilot design, but cannot upgrade a local warehouse metric's evidence status. |
| D-39 | Active | **No source, no numeric fact.** Medical/Financial concepts without verified encounter or claim sources remain gap rows, not NULL/zero KPI views. |
| D-40 | Approved target | **Numerator and denominator must be auditable in the same metric relation.** Eligibility, censoring, source frontier, `data_as_of`, non-empty/fresh-period checks, and small-cell behavior are part of the definition. |
| D-41 | Approved target | **A different denominator, population, eligibility rule, grain, or time alignment is a different metric definition.** Assign a new semantic version or metric ID; do not hide the change behind a chart label. |
| D-42 | Active | **Observed facts, external evidence, and scenarios are separate evidence objects.** A simulation, forecast, or valuation never inherits `OBSERVED` status from its inputs and must carry an assumption version, owner, range or sensitivity, and provenance. |
| D-43 | Active | **Shared vocabulary or schema does not establish a shared population or a valid identity join.** Cross-deployment joins require a source-backed identity map, compatible as-of contract, and row-loss reconciliation; FHIR/USCDI labels alone satisfy none of these. |

## 4. Model-family contract

The table records the current family contract; P4/P5 rows remain target work
where stated.

| Family | Contract |
|---|---|
| `dim_date`, `dim_disease`, `dim_action`, `dim_device_type`, `dim_deployment_site` | Keep, subject to current graph tests |
| `dim_user` | One row per user; stable/current profile only; no lifetime `is_observable_*` behavior |
| current site | `bridge_user_site_current.current_site_id`; no historical meaning |
| `fct_user_milestone` | Atomic user × milestone lifecycle fact with honest temporal precision |
| `fct_app_action` | Keep; control semantic overlap through a versioned event taxonomy |
| search/share facts | New source unique-index-grain facts; retain neutral semantics where source meaning is unknown |
| `fct_coaching_event` | Keep delivered/responded/completed states separate |
| `fct_measurement` | Keep, after device/transaction grain conflict remeasurement |
| `fct_user_disease_day` | Keep as a derived IRS-score fact; ranks are not additive |
| `fct_wearable_day` | Keep as sparse daily intensity in core |
| `fct_user_day` | Rebuild from canonical facts with channel completeness/frontiers |
| `fct_user_month` | New user × calendar/relative-month panel with partial/right-censored flags |
| `fct_user_day_wide` | Serving relation only after future-information flags are removed |
| six `fct_wearable_*` facts | Move to restricted `marts_detail` and exclude from daily core |
| existing `v_pi_*` | Legacy candidates; P5 records keep/replace/retire before publication |
| `v_bridge_pi_to_kpi` | Retain only as a source-gap register, never a causal substitute |

## 5. Rejected and superseded approaches

| Approach | Reason |
|---|---|
| Bare full dbt build as the routine unit | It couples cheap core work to expensive detail work and contributed to the storage incident. |
| Freshness warning followed by build | Stale data can manufacture false zeros and invalid denominators; freshness is a gate. |
| Blind retry after a resource failure | It repeats the resource pressure that caused the failure. |
| Full-table materialization as one global policy | Cost and late-arrival behavior differ by model family. |
| Runtime-only “15 minute” threshold | It ignores temp spill, storage headroom, concurrency, and impact on the shared endpoint. |
| One omnibus event or accumulating snapshot | Search, share, coaching, measurement, site, milestones, and scores do not share one honest grain. |
| Lifetime behavior flags in `dim_user` | They leak future outcomes into historical rows. |
| Current site joined as historical site | Source in-place updates erased prior value and switch time. |
| Metric prefixes as the whole contract | A prefix does not define denominator, eligibility, censoring, freshness, evidence, or ownership. |
| Reusing one metric ID after changing its denominator or population | The result answers a different question and breaks longitudinal interpretation. |
| Treating W-A/B/C/D as one causal funnel | The families have different populations, milestones, denominators, and evidence strength. |
| Treating a shared schema or FHIR label as an identity join | Vocabulary alignment does not prove person identity, deployment compatibility, or row reconciliation. |
| Promoting an external effect size or scenario output as a local observed KPI | Literature and models can motivate hypotheses; they do not create a local source event or causal result. |
| Fabricated Medical/Financial KPI views | No encounter/claim source exists; NULL or zero invites false citation. |
| IRS-family addition/subtraction | The scores are ranks and are not components of an arithmetic decomposition. |
| General BI access to wearable detail | It increases exposure and resource risk without a general reporting consumer. |
| A local machine as production | It has no durable identity, dependency, backup, or operational ownership. |

## 6. Open owner contracts

Owner decisions are maintained in [`HANDOVER.md`](HANDOVER.md) with safe defaults. Until a
decision is recorded, the affected public metric or sensitive data path remains withheld.

Technical representation choices that preserve these semantics—such as current-site column
versus current bridge, exact intermediate naming, or selector syntax—do not require an owner
decision.
