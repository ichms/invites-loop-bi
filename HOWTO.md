# HOWTO: safe changes during the W-first recovery

This guide describes safe repository and warehouse procedures under the
recovery contract in [todo.md](todo.md). It does not authorize skipping a phase
gate.

As of 2026-08-21:

- P0 through P4 are complete and recovery continues at P5;
- P3 targeted builds populated dimensions, atomic facts, milestones, and the
  daily/month panels; the complete <code>daily_core</code> recovery remains P6;
- Superset has not been refreshed or accepted against the P3 relations;
- <code>daily_core</code>, <code>wearable_detail</code>,
  <code>intermediate_private</code>, and <code>marts_detail</code> are implemented;
  the lifecycle/panel redesign and reusable heart-rate dedupe are implemented,
  while the metric registry is not;
- the current transform DAG is not safe to run unattended.

Never copy an old command merely because it worked against the previous graph.

## 1. Know which operations are allowed

| Phase | Allowed work |
|---|---|
| P0 | Config, tests, PII documentation, reviewed cleanup SQL preparation, offline tests, dbt parse/compile |
| P1 | Narrow source/staging/atomic-fact builds after exact selection review |
| P2 | Selector, schema, materialization, and grant-boundary implementation |
| P3 | Narrow dimension, lifecycle, daily, and monthly panel builds |
| P4 | Controlled heart-rate intermediate/detail work with storage measurement |
| P5 | Narrow registry and metric-view builds |
| P6 | First complete measured <code>daily_core</code> recovery and explicit Superset refresh |
| P7 | Scheduler, dependency, alerting, backup, and runbook activation |

Until P0 through P5 pass, do not run a bare/full dbt graph, activate the
transform DAG, bulk-register marts in Superset, perform a new manual watermark
deletion, or execute wearable detail without storage controls.

## 2. Start every change with a preflight

### Inspect the worktree

The original 2026-08-21 search/share changes are uncommitted and must survive.

~~~bash
git status --short
git diff -- src/invites_loop_bi/config/iccoli_targets.py
git diff -- tests/extract/test_config_targets.py
~~~

Inspect any file you plan to edit. Do not use commands that reset or clean the
worktree.

### Run non-mutating validation

~~~bash
INVITES_LOOP_BI_TEST_OFFLINE=1 uv run pytest
source setup_env.sh
uv run dbt parse --project-dir dbt
uv run dbt compile --project-dir dbt
~~~

Parse and compile validate project structure; they do not prove data freshness,
grain, reconciliation, or permission correctness.

### Inspect a narrow dbt selection

For any targeted model build during P0 through P5:

~~~bash
uv run dbt ls --project-dir dbt --select model_name
~~~

Review every selected node. Confirm that the selection does not include
heart-rate aggregation, any source-grain wearable fact, or an unreviewed parent
or child expansion.

Only then may a small targeted build run:

~~~bash
uv run dbt build --project-dir dbt --select model_name --threads 1 --fail-fast
~~~

Do not use an unreviewed <code>+</code> expansion. Record the expected source
count, row-loss explanation, grain, and reconciliation before the build.

## 3. Add or change an extraction target

An extraction target is a data-retention and mutation contract, not just a
table name.

### Step 1: measure the source read-only

Before editing config, record:

- primary key and whether it is actually unique;
- row count and actor count, with extraction timestamp;
- nullable columns;
- timestamp types and business timezone;
- insert, update, and delete behavior;
- whether updates change the proposed watermark;
- actor-key meaning and cohort mapping;
- direct identifiers, free text, tokens, fingerprints, external keys, and
  sensitive payloads;
- expected size and backfill behavior.

A source with observed in-place UPDATEs and no trustworthy update timestamp is
not safe for creation-time incremental extraction. Use a filtered full refresh
when it is small enough.

### Step 2: define the minimal target

Targets live in
<code>src/invites_loop_bi/config/&lt;system&gt;_targets.py</code>.

The target contract may include:

- <code>load_type: full_refresh</code>;
- <code>row_filter</code> for source-side cohort restriction;
- <code>exclude_columns</code> for fields that must never land;
- a watermark and fallback only when mutation behavior supports them;
- bounded lookback for late-arriving streams.

For analytical and user-event iccoli data, preserve the Loop-only actor filter.
A different actor column, such as <code>from_user_no</code>, needs an equivalent
explicit filter rather than the default <code>user_no</code> predicate. The
deliberately unfiltered <code>tb_ext_user_mapper</code> is the identity bridge
that defines and translates the cohort, not an analytical event target.

For the new search/share targets, P0 requires these exclusions:

| Source field | Reason |
|---|---|
| <code>tb_search_log.word</code> | user-entered free text |
| <code>tb_share_info.share_key</code> | access-token-like key |
| <code>tb_share_log.share_key</code> | access-token-like key |
| <code>tb_share_log.to_user_ip</code> | direct network identifier |
| <code>tb_share_log.to_user_agent</code> | device/browser fingerprint |
| <code>tb_share_log.to_user_no</code> | may identify a non-Loop recipient |

Keep <code>tb_share_info.target_no</code> out of general marts until its
meaning and FK/PII policy are approved for each <code>share_type</code>.

### Step 3: test the config contract

Tests should prove:

- total and per-system target counts;
- the correct load type;
- actor filters on all analytical and user-event targets, with the mapper
  exception asserted explicitly;
- the full exclusion set;
- no duplicate target declarations;
- expected primary-key/no-primary-key classification.

Do not pin a volatile source row count as a permanent test constant.

### Step 4: handle already-landed prohibited columns

Adding an <code>exclude_columns</code> entry prevents future extraction but does
not remove an existing landing column.

Prepare a separate, reviewable SQL migration that:

1. proves no downstream dependency needs the field;
2. records the exact schema, table, and column targets;
3. removes only those reviewed fields;
4. contains post-change verification queries;
5. can be reviewed without executing it.

Do not execute the cleanup during documentation review or before its P0 review
gate. Do not broaden it to unrelated landing rows, tables, or watermarks.

### Step 5: regenerate the PII inventory

After the 128-target config and reviewed cleanup state agree, regenerate
[PII_INVENTORY.md](PII_INVENTORY.md) from the current landing catalog. Clearly
separate current retained columns from historical cleanup evidence.

The loader automatically adds new upstream columns. Treat added-column logs and
every target-config change as inventory-review triggers.

## 4. Add a dbt source and staging model

### Step 1: declare the source

Add the landing table to the appropriate
<code>dbt/models/staging/src_&lt;system&gt;.yml</code>.

Freshness must reflect source mutation and actual cadence. A quiet incremental
event table is not a useful heartbeat merely because it has
<code>_loaded_at</code>. Choose a source that can prove the EL ran, and make
required freshness a hard gate before P6/P7 transforms.

### Step 2: create a PII-safe staging projection

A staging model should:

- cast source types explicitly;
- deduplicate according to measured source behavior;
- translate source user serials to canonical <code>user_id</code>;
- retain the original timestamp and an explicit KST business date;
- select only approved analytical columns;
- omit raw source user serials after translation;
- omit direct identifiers, free text, tokens, fingerprints, and external
  recipient keys;
- filter or count unmapped actors explicitly rather than dropping them
  silently.

Marts reference staging models through <code>ref()</code>; they do not select
directly from a landing schema.

### Step 3: test staging

At minimum, test:

- source-PK uniqueness and not-null behavior;
- actor mapping to Loop users;
- cast integrity;
- source-to-staging row reconciliation;
- expected, explicitly explained losses;
- JSONB allow-list drift where a payload is flattened;
- prohibited-column absence.

For search/share, also test that every interaction joins to its share link by
<code>share_no</code> and detect orphan or sender-mismatch drift without
hard-coding the current zero count as eternal truth.

## 5. Add an atomic fact

### Step 1: declare the grain in SQL

Every fact begins with a grain contract.

~~~sql
-- GRAIN: one row per source_event_id.
-- PURPOSE: one source-shaped event; no cross-source deduplication.
-- TIME: source timestamptz plus explicit KST business date.

with staged as (

    select *
    from {{ ref('stg_system__source_table') }}

),

cohort as (

    select user_id
    from {{ ref('dim_user') }}

)

select staged.*
from staged
inner join cohort using (user_id)
~~~

The cohort join is a policy guard, but it can remove mapper-only actors. Measure
and test that difference. Do not call silent loss “cleaning.”

### Step 2: declare grain and FK tests

~~~yaml
- name: fct_example_event
  description: "GRAIN: one row per source_event_id."
  data_tests:
    - dbt_utils.unique_combination_of_columns:
        arguments:
          combination_of_columns: [source_event_id]
  columns:
    - name: source_event_id
      data_tests:
        - not_null
    - name: user_id
      data_tests:
        - not_null
        - relationships:
            arguments:
              to: ref('dim_user')
              field: user_id
    - name: event_date
      data_tests:
        - not_null
        - relationships:
            arguments:
              to: ref('dim_date')
              field: date_day
~~~

Add source-to-fact reconciliation, not just uniqueness and FK tests.

### Step 3: keep event meanings separate

For the new facts:

- <code>fct_app_search_event</code> has search-event grain;
- <code>fct_share_link</code> has created-share-link grain;
- <code>fct_share_interaction_event</code> has follow-up-interaction grain.

Do not sum those three row counts into one “share count.” Do not merge new share
events into <code>fct_app_action</code> until the overlap taxonomy is measured
and versioned. Do not cross-source deduplicate merely because two events sound
similar.

Until the business meaning is approved, a share interaction is a neutral event
and does not make the sender active on that day.

## 6. Place models in the correct target layer

P2 implemented these target boundaries on 2026-08-21.

| Target layer | Intended contents | General Superset access |
|---|---|---|
| <code>staging</code> | casts, dedupe, key translation, safe projection | no |
| <code>intermediate_private</code> | reusable expensive heart-rate dedupe/aggregation | no |
| <code>marts</code> | dimensions, atomic core facts, dense panels, thin metric/serving views | yes, after P6 verification |
| <code>marts_detail</code> | six source-grain wearable observation facts | no |

A model belongs in core only if the daily product needs it at ordinary cadence.
A named analyst need does not make an observation-level table a daily-core
dependency.

### Inspect the implemented selectors

The tags and <code>selectors.yml</code> definitions for
<code>daily_core</code> and <code>wearable_detail</code> are implemented. Before
any selector build, inspect them and run the boundary assertion:

~~~bash
uv run dbt ls --project-dir dbt --selector daily_core
uv run dbt ls --project-dir dbt --selector wearable_detail
scripts/assert_p2_selector_boundaries.sh
~~~

The core listing must exclude all six source-grain wearable facts and their
dedicated heavy tests. It may still consume daily wearable intensity, so P4
must first make the raw heart-rate aggregation reusable rather than repeating
it.

Do not run the complete <code>daily_core</code> selector before P6. Do not run
<code>wearable_detail</code> before the P4 storage preflight and measured detail
procedure. Selector existence is not execution authorization.

## 7. Maintain dense daily and monthly panels

<code>fct_user_day</code> remains the canonical dense behavioral panel.

When adding a channel:

1. add the channel's canonical atomic fact or daily aggregate;
2. define its observed frontier and load completeness;
3. extend the lower bound for real pre-enrolment activity;
4. distinguish eligible observed zero from stale/not-loaded unknown;
5. add the channel to
   <code>assert_user_day_spine_loses_no_activity</code>;
6. reconcile atomic fact totals to daily totals;
7. carry the denominator pair needed by downstream rates.

Do not rebuild panel channels directly from landing or duplicate staging
aggregations when a canonical fact already exists.

<code>fct_user_month</code> must remain user × calendar/relative month and carry
partial-month and right-censoring indicators. Preserve both numerator and
denominator components rather than storing only a rate.

Do not place lifetime “ever did X” outcomes into
<code>fct_user_day_wide</code>. That leaks future behavior into earlier rows.
Serving relations may pre-join stable or explicitly current attributes, but
must label current site as current and never imply historical attribution.

## 8. Build the heart-rate path safely

P4 made one physical deduplicated heart-rate relation reusable by
<code>fct_wearable_day</code>, detail facts, attribution, and reconciliation.

The contract must preserve:

- exact duplicate multiplicity as <code>source_row_count</code>;
- <code>n_samples = sum(source_row_count)</code>;
- multiplicity-weighted mean equivalence;
- min/max equivalence;
- user/date daily equivalence;
- bounded 30-day incremental or window-replace behavior;
- an explicit measured full-refresh path for older corrections;
- equality between incremental and full-refresh results.

Before any large execution, record Azure Monitor storage. Warn at 70% used and
do not start at 80% used. Use one thread. Record pre-run, peak, and post-run
storage, PostgreSQL database-size delta, <code>temp_bytes</code> delta, permanent
relation size, and node runtime.

Never treat the database-size query as a substitute for Azure free-space
measurement.

Routine heart-rate processing uses exact model selections in this order:

```bash
source setup_env.sh
uv run dbt ls --project-dir dbt \
  --select stg_discovery__lifelog_wearable_heartrate \
  --resource-type model
uv run dbt run --project-dir dbt \
  --select stg_discovery__lifelog_wearable_heartrate \
  --threads 1 --fail-fast
uv run dbt run --project-dir dbt \
  --select stg_discovery__lifelog_wearable_day \
  --threads 1 --fail-fast
```

Do not replace the first command with an unreviewed `dbt build`: indirect test
selection includes the intentionally expensive P4 audit and detail-only
reconciliation. Run the full-source audit explicitly only under the same Azure
gate:

```bash
uv run dbt test --project-dir dbt \
  --select assert_heartrate_full_calculation_equivalence \
  --threads 1 --fail-fast
```

For a correction older than 30 days or a lifelog-user mapping change, run the
dedupe and wearable-day commands with `--full-refresh`, then run the audit. A
source-grain detail build additionally requires a named consumer and access
approver; inspect `--selector wearable_detail`, recheck Azure immediately, and
run it separately with one thread. Never couple it to `daily_core`.

The 2026-08-21 measured baseline was: full dedupe 68.32 seconds, 30-day
replacement 58.33 seconds, full wearable-day 10.86 seconds, incremental
wearable-day 5.23 seconds, and audit 16.95/15.53 seconds. The landing table has
no `measured_dt` index, so the bounded incremental query still scans the 791 MB
landing relation even though it groups and rewrites only the recent window.

## 9. Add or change a public metric

P5 must add a git-tracked metric registry before the W-A/B/C/D views become
public.

Every registry row needs:

- semantic <code>metric_id</code> and <code>metric_version</code>;
- tier, <code>evidence_status</code>, and evidence provenance;
- population or deployment scope, entity, and grain;
- aggregation, numerator, denominator, and eligibility;
- time alignment, censoring rule, and timezone;
- source frontier and <code>data_as_of</code>;
- assumption version for a derived model, hypothesis, scenario, or forecast;
- small-cell rule;
- metric owner and decision owner.

Use <code>OBSERVED</code>, <code>DERIVED</code>,
<code>HYPOTHESIS</code>, or <code>ROADMAP</code>. Do not encode changing slide
numbers such as “KPI 1” into model or metric IDs.

A change to population, denominator, eligibility, grain, or time alignment is
a semantic change. Create a new metric version or ID instead of relabelling the
old result. A simulation, forecast, or valuation is never <code>OBSERVED</code>,
even when all of its inputs are observed.

Keep one public metric definition per thin view. The SQL and registry must agree
on denominator, eligibility, censoring, and evidence status. Add tests for a
fresh/non-empty reporting period; aggregate not-null tests alone pass when a
view has zero rows.

### Safe defaults for unresolved semantics

| Unresolved meaning | Safe implementation |
|---|---|
| Activation event | Keep raw milestones; withhold activation rate |
| 30/90-day retention event/window | Withhold retention |
| Share interaction or <code>point_call_yn</code> | Neutral interaction; never “open” or “success” |
| Raw search terms | Exclude |
| External recipients | Do not retain keys |
| Remote-care qualifying day | <code>HYPOTHESIS</code>; no revenue/billing claim |
| Measurement eligibility | Counts only; no participation/adherence rate |
| Historical site | Prohibit attribution |
| Medical/Financial KPI | <code>ROADMAP</code> gap only |

IRS score movement is derived validation evidence, not a clinical effect.
Behavior-to-risk views must declare exposure and outcome windows, minimum sample
size, and non-causal language.

## 10. Recover the core in P6

Run this section only after the P0–P5 completion criteria in
[todo.md](todo.md) pass and the selectors have been inspected.

### Preflight

- Verify completion for all five EL sources.
- Run required source freshness as a hard gate.
- Record Azure Monitor used/free storage.
- Stop at 80% used; review expected peak at 70% or higher.
- Record database size and <code>temp_bytes</code>.
- Save the exact <code>daily_core</code> node listing.

### Core execution

~~~bash
source setup_env.sh
uv run dbt source freshness --project-dir dbt
uv run dbt build --project-dir dbt --selector daily_core --threads 1 --fail-fast
~~~

Record model/test runtime, failing node, storage peak, and row counts from
dimensions through atomic facts, panels, and metrics. Acceptance means every
node selected by the current graph is green; it does not mean reproducing an
old node count.

Then run the full live Python suite and generate dbt documentation:

~~~bash
uv run pytest
uv run dbt docs generate --project-dir dbt --static
~~~

Review lineage in <code>dbt/target/static_index.html</code>.

### Optional detail execution

Run detail only for a named need, after a new storage check:

~~~bash
uv run dbt build --project-dir dbt --selector wearable_detail --threads 1 --fail-fast
~~~

Core success and detail success are independent statuses.

## 11. Expose reviewed data to Superset

Do not refresh Superset datasets during P0 through P5. The current marts are
empty, and the relation set will change.

In P6:

1. produce an explicit allow-list of recovered core/serving relations;
2. verify each relation's grain, PII projection, evidence status, and
   <code>data_as_of</code>;
3. verify <code>superset_reader</code> can read only <code>marts</code>;
4. verify it cannot use landing, staging, private intermediate, or
   <code>marts_detail</code> schemas;
5. register only the explicit allow-list;
6. remove or update datasets and charts that reference retired/renamed metrics;
7. smoke-test representative W-A/B/C/D queries and charts;
8. display the latest successful EL/build time and evidence status.

Do not use a script that scans and registers every relation in every analytic
schema. Superset does not infer semantic safety from a schema name.

A chart reads one dataset. Repeated cross-table business logic belongs in a
tested dbt serving relation, not in chart-specific joins or duplicated virtual
datasets.

## 12. Join and interpret relations safely

### Avoid fan-out

A dimension-to-fact join is safe only when the dimension is unique on the join
key. A fact-to-fact join on <code>user_id</code> alone usually multiplies rows.
Join facts on their full shared grain or aggregate one side first.

### Use dates deliberately

Join a timestamp through its explicit business-date column, not directly to
<code>dim_date.date_day</code>. Preserve the original timestamp for ordering
and traceability.

### Treat current site as current

Use <code>current_site_id</code> or
<code>bridge_user_site_current</code> only for current-population filtering.
Never label an old action, score, coaching event, or measurement with that
current site as though it were event-time history.

Do not add site to the user × day grain. A multi-affiliated user would duplicate
every daily measure.

### Keep score math honest

IRS, IRS+, LRS, MRS, and PRS are 1–100 ranks. Do not sum them, subtract them, or
invent a residual. Aggregate first at the user × disease × period grain before
population weighting. Distinguish any-high-risk-in-month from the latest or
month-end risk state.

### Check coverage and censoring

A trend is uninterpretable without the eligible population, scoring/measurement
coverage, source frontier, and right-censoring rule. Retrieve those fields from
the same metric contract as the numerator.

## 13. Restrict database, Superset, and AI access

The database role is the enforcing access boundary for every client, including
Superset, notebooks, SQL tools, and AI connectors.

- Use a dedicated read-only role with only the required schema grants.
- Never give a general BI or AI client the dbt/warehouse-owner credentials.
- Do not rely on an application role to hide a schema the connection itself can
  read.
- Do not give an automated client Superset Admin merely to query data.
- Keep SQL timeouts and read-only transaction settings as defense in depth.
- Keep credentials and secret values out of commands, logs, screenshots, and
  documentation.

Role restriction does not replace minimization. EL exclusions, staging
projections, JSONB allow-lists, core/detail schema separation, small-cell rules,
and database grants work together.

## 14. Make operation unattended only in P7

A fixed one-hour schedule offset is not a dependency. P7 must make transform
wait for successful completion of all five EL sources and must prove even empty
incremental runs completed.

The unattended transform must:

- hard-fail on required source freshness;
- run an Azure storage preflight;
- select <code>daily_core</code>;
- use one thread and fail-fast;
- keep <code>max_active_runs=1</code>;
- avoid blind whole-build retry after storage/resource failure;
- send source, freshness, storage, and dbt-node context in alerts;
- run from the approved Azure location and service identity, not a local
  machine.

Before activation, assign owners for the scheduler, alerts, Airflow metadata DB,
Superset app DB, backup/restore, secrets, warehouse roles, and safe reruns.
Document the procedures in an English operational runbook and verify that a
successor can use it without repository-author assistance.

## 15. Troubleshooting rules

| Symptom | First interpretation |
|---|---|
| Unique-grain test fails | Source or join grain changed; do not delete the test |
| JSONB drift test fails | Classify the new key before deciding whether it may be extracted |
| Metric view returns zero rows | Treat as failure unless zero rows are explicitly valid and freshness proves it |
| Recent activity falls to zero | Check per-channel load completeness and frontier before interpreting behavior |
| Current-site totals look historical | The wrong site semantics were used |
| Share totals disagree | Confirm whether the query counts links, interacted links, or interaction events |
| Core selection includes raw wearable facts | Selector boundary is wrong; stop before build |
| Storage reaches 80% | Do not start a new build. For one already running, follow the reviewed incident/runbook procedure; do not invent an automatic abort or continue policy |
| Detail build fails after core passed | Preserve core success; diagnose detail separately |
| New landing column appears | Trigger PII classification and target-contract review |
| Superset cannot see a new core relation | Verify P6 allow-list registration and grants; do not broaden schema access |
