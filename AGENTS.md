# AGENTS.md

## Authority and document roles

This repository is in a controlled redesign and recovery. Read [todo.md](todo.md)
before changing code, models, grants, orchestration, or operational data.

When statements conflict, use this order:

1. facts measured from the current source or landing data;
2. grain, reconciliation, freshness, and PII tests;
3. the gates and acceptance criteria in [todo.md](todo.md);
4. the rationale in [INVITES_LOOP_BI_DECISION_LOG.md](INVITES_LOOP_BI_DECISION_LOG.md);
5. dated findings in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md);
6. strategy and older design material under <code>docs/</code>.

The ignored strategy archive describes historical intent and research. Its
<code>LOCKED</code>, <code>FROZEN</code>, or <code>SSOT</code> labels do not
override this authority order, and it does not prove that a source, population,
identity join, grain, denominator, or clinical outcome exists. Preserve the
archive as provenance. Promote only durable rules into tracked English
documents, and never promote an archived number without current source,
grain, reconciliation, and evidence support.

Document responsibilities are deliberately separate:

- [todo.md](todo.md): current execution contract and phase gates;
- this file: stable repository architecture and engineering rules;
- [INVITES_LOOP_BI_DECISION_LOG.md](INVITES_LOOP_BI_DECISION_LOG.md): current
  decisions and rationale;
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md): dated measurements and
  superseded assumptions;
- [PII_INVENTORY.md](PII_INVENTORY.md): data classification and retention scope;
- [HANDOVER.md](HANDOVER.md): current recovery and operational handover;
- [HOWTO.md](HOWTO.md): safe operational recipes.

## Project

<code>invites-loop-bi</code> is an OLAP ELT pipeline. It extracts data from five
operational PostgreSQL source systems, loads warehouse landing schemas, and uses
dbt Core to transform that data for BI. The Airflow DAG files live in
<code>dags/</code>. Python is 3.13 or later, dependencies are managed with
<code>uv</code>, and package code uses a <code>src/</code> layout.

The Python entry point is <code>src/invites_loop_bi/pipeline.py</code>.

### Current state: 2026-08-21 KST

The current state is not the old completed-state narrative:

- The configured extraction estate contains 128 targets: iccoli 37, ichms 16,
  sibc 36, irs 5, and discovery 34.
- All 128 rows in <code>stg_meta.watermarks</code> are currently
  <code>SUCCESS</code>.
- EL was run manually through the 2026-08-21 08:00 KST source cutoff.
- P3 targeted builds restored redesigned dimensions, atomic facts, milestones,
  an 81,745-row user-day panel, and a 2,996-row user-month panel. This was not a
  complete <code>daily_core</code> recovery build. Six source-grain wearable
  facts remain empty in <code>marts_detail</code>; metric views are still legacy
  candidates, and Superset has not been refreshed or accepted against the
  redesign.
- P4 materialized the reusable 9,010,144-row heart-rate payload dedupe and the
  47,046-row incremental wearable-day aggregate. Full-source audits passed
  after both full refresh and 30-day window replacement. The six detail facts
  remain unbuilt because there is no named consumer.
- Historical results such as dbt 388/388 and pytest 125/125 are evidence about
  an older graph, not current acceptance criteria.
- The current offline Python baseline is 95 passed and 32 skipped. The live
  suite has not been rerun.
- EL and dbt have only been invoked manually. Schedules are declared in code,
  but no scheduler is deployed and no DAG has run unattended.
- P0 through P4 are complete. The W-first redesign continues at P5.

The 128-target configuration contract and its 37/16/36/5/34 per-system split
are intentional test invariants. Do not hard-code volatile source, landing, or
mart row counts; reconcile those dynamically and label any quoted measurement
with its extraction date.

### Preserve the existing worktree

At the start of the 2026-08-21 recovery, the <code>main</code> baseline was
commit <code>35b0ed4</code>. The following pre-existing changes belong to the
current task and must not be overwritten or reverted:

- <code>.gitignore</code>: make <code>todo.md</code> trackable;
- <code>dags/elt_to_staging.py</code>: iccoli target count 34 to 37;
- <code>src/invites_loop_bi/config/iccoli_targets.py</code>: three search/share
  targets;
- <code>tests/extract/test_config_targets.py</code>: cohort-filter and PII
  assertions;
- <code>todo.md</code>: the recovery contract.

Always inspect <code>git status --short</code> and the relevant diffs before
editing overlapping files. Do not commit, push, deploy, or discard work unless
explicitly requested.

## Safety gates

P0 through P5 must finish before the first complete core recovery build.

Until then, do not:

- run a bare or full-graph dbt build;
- activate <code>transform_dbt_build</code> or start a scheduler;
- run global marts dataset registration in Superset;
- perform additional landing truncation, landing deletion, or manual watermark
  deletion;
- start a large query or wearable-detail build without checking Azure storage;
- use a user's current site as the site of a historical event.

The current transform DAG is unsafe for unattended use: it runs the whole graph,
does not set a thread limit, ignores freshness failure, and retries the whole
build once after failure. P7 must correct all four behaviors.

These commands inspect files or compile the graph without creating database
relations:

~~~bash
git status --short
git diff -- src/invites_loop_bi/config/iccoli_targets.py
git diff -- tests/extract/test_config_targets.py
INVITES_LOOP_BI_TEST_OFFLINE=1 uv run pytest
source setup_env.sh
uv run dbt parse --project-dir dbt
uv run dbt compile --project-dir dbt
~~~

During P0 through P5, a small targeted model build is allowed only when all of
the following are true:

1. inspect the exact selection first with <code>dbt ls</code>;
2. name the model explicitly;
3. confirm that no heart-rate or wearable-detail path is selected;
4. use one thread and fail fast;
5. record the intended reconciliation before mutating the warehouse.

~~~bash
uv run dbt ls --project-dir dbt --select model_name
uv run dbt build --project-dir dbt --select model_name --threads 1 --fail-fast
~~~

Do not use an unreviewed <code>+</code> parent or child expansion.

The <code>daily_core</code> and <code>wearable_detail</code> selectors are target
state, not current capability. They must be implemented and inspected in P2
before either selector is run.

### Storage stop lines

The operational databases and <code>invites_dw</code> share one PostgreSQL
endpoint and therefore share storage, I/O, and CPU. The 2026-08-20 incident was
triggered by repeated aggregation of roughly nine million landing heart-rate
rows overlapping a full rebuild of roughly 8.9 million detail rows.

Azure storage was increased from 128 GB to 256 GB, but that is temporary
headroom rather than resource isolation. Use Azure Monitor as the stop-line
source:

| Azure storage used | Rule |
|---|---|
| below 70% | execution may proceed with measurement |
| 70% or above | warn and review expected peak plus operational load |
| 80% or above | do not start a new dbt build |

PostgreSQL database size and <code>temp_bytes</code> are useful deltas, but they
do not represent free space on the Azure filesystem.

## Execution gate summary

The detailed checklist and completion tests live in [todo.md](todo.md). This
summary does not replace them.

| Phase | Gate |
|---|---|
| P0 | Preserve existing changes; move the three new targets to filtered full refresh; enforce EL PII exclusions; regenerate the 128-target inventory; pass offline tests |
| P1 | Add sources, staging models, atomic search/share facts, source unique-index grain tests, actor mapping, and row-loss reconciliation |
| P2 | Implement and inspect core/detail selectors, schemas, grants, and registration boundaries |
| P3 | Separate stable profile, current site, milestones, lifecycle facts, channel-aware daily/month panels, and unknown versus observed zero |
| P4 | Materialize reusable heart-rate dedupe and prove incremental/full-refresh equivalence and weighted reconciliation |
| P5 | Add the versioned metric registry and W-A/B/C/D views with evidence, denominator, censoring, and freshness contracts |
| P6 | After P0–P5, perform the measured single-thread core recovery, tests, documentation, and explicit Superset refresh |
| P7 | Add real EL dependencies, hard freshness and storage gates, an Azure scheduler runtime and service identity, alerts, backup ownership, and a runbook |

Do not begin database mutation for a later phase until the preceding phase's
completion conditions pass.

## EL architecture

The current Python path is Extract → Load → Commit.

### Streaming contract

Rows never become Python objects. Extraction streams PostgreSQL
<code>COPY (SELECT ...) TO STDOUT (FORMAT csv)</code> into a spooled buffer, and
the loader streams that buffer through <code>COPY ... FROM STDIN</code>. This
preserves PostgreSQL's text representation for JSONB, arrays, enums,
<code>numeric</code>, and intervals while avoiding row-wise inserts.

Do not reintroduce a dataframe on this path without revisiting
<code>extract/introspect.py</code>. A dataframe schema union can silently alter
heterogeneous JSONB objects.

### Ordering and watermarks

<code>extract() → load() → commit()</code> is the core invariant.

- A watermark moves only after staging rows commit.
- A failure records the error without advancing the watermark.
- The next run replays the same window.
- The new watermark is the highest value among rows actually loaded, not a wall
  clock.
- A first empty extraction uses the source clock only because otherwise it
  would full-load forever.
- Source sessions are read-only; warehouse autocommit is off.

A watermark proves business position for one target. It does not prove that a
whole DAG completed, especially when an incremental run was empty. P3 decides
and models the required load-completion evidence; P7 implements it in the
orchestration path.

### Introspection and load strategies

Source columns and primary keys come from the source catalog. Unsupported
warehouse types become text. New upstream columns are automatically added to
landing tables; dropped or retyped columns are logged, not repaired
automatically. Treat every added-column log as a PII review trigger.

| Target shape | Load behavior |
|---|---|
| Declared full refresh, with or without a primary key | truncate and insert in one transaction; this overrides primary-key handling |
| Incremental with a primary key | upsert; redelivered rows overwrite |
| Incremental without a primary key | delete the extracted watermark window, then insert |

Every landing table has <code>_loaded_at timestamptz</code>.

### Target configuration

Targets live in
<code>src/invites_loop_bi/config/&lt;system&gt;_targets.py</code>. Adding a
source table is a configuration and policy change, not a new pipeline
implementation.

A target may declare:

- source schema and table;
- primary and fallback watermark columns;
- <code>load_type: full_refresh</code>;
- <code>exclude_columns</code>;
- a source-side <code>row_filter</code>;
- a bounded lookback for late-arriving streams.

All analytical and user-event iccoli targets must keep the Loop-cohort source
filter. The deliberately unfiltered <code>tb_ext_user_mapper</code> is the
identity bridge used to define and translate that cohort; it is not an
analytical event target. Community-app users must not leave the source system
through the filtered targets.

The three new search/share targets are filtered full refresh because UPDATEs
were observed without a trustworthy update watermark. Their actor filters and
complete PII exclusions are P0 contracts and must be preserved.

## Transform architecture

### Current shape

dbt currently reads the five <code>stg_&lt;system&gt;</code> landing schemas,
builds views in <code>staging</code>, and has P3 core relations plus legacy
metric views in <code>marts</code>. The complete core graph has not been rebuilt,
and the legacy metric views are not accepted public definitions.

### Target shape

~~~text
stg_* landing
  -> staging views: cast, dedupe, key translation, PII-safe projection
  -> private physical intermediates: reusable expensive dedupe/aggregation
       |-> marts: dimensions, atomic core facts, daily/month panels, serving views
       `-> marts_detail: source-grain wearable observations for analysts only
~~~

Only <code>marts</code> is the general BI surface.
<code>superset_reader</code> must have no access to landing,
<code>staging</code>, private intermediates, or <code>marts_detail</code>.

### Modeling rules

1. Every fact declares its grain in its SQL header and has a unique-grain test.
2. <code>fct_user_day</code> remains a dense panel with real zero days.
3. Its upper bound is an observed frontier, never <code>current_date</code>.
4. Actual activity before enrolment extends the spine to that earlier date.
5. <code>assert_user_day_spine_loses_no_activity</code> remains and expands to
   every canonical channel.
6. Marts expose <code>user_id</code> as the user key; source serial user keys
   are translated in staging.
7. Direct identifiers, free text, access tokens, and unnecessary external user
   keys never enter general marts.
8. Do not merge source-shaped events into an omnibus snapshot.
9. A metric relation must make its numerator and denominator jointly
   verifiable.
10. A zero is not inactivity when a channel is stale, ineligible, or not yet
    loaded; represent completeness and eligibility explicitly.
11. Current site is a current filter only, never event-time history.
12. IRS, IRS+, LRS, MRS, and PRS are 1–100 ranks. Never add them or manufacture
    a residual.
13. Keep one public metric definition per view and review it in git.
14. Daily core and wearable detail are separate build and permission units.
15. Do not call association, risk-score movement, or app behavior a causal or
    clinical effect.
16. Medical and Financial metrics without encounter, admission, claim, or
    billing sources remain roadmap gaps rather than numeric facts.

## PII and access controls

PII protection is layered:

1. **Source/EL boundary:** cohort row filters and
   <code>exclude_columns</code> prevent unnecessary data from landing.
2. **dbt staging boundary:** projections, key translation, and JSONB
   allow-lists prevent sensitive fields from entering analytic models.
3. **Schema boundary:** core, private intermediate, detail, staging, and landing
   schemas have distinct audiences.
4. **Database-role boundary:** <code>superset_reader</code> is read-only and
   restricted to <code>marts</code>.
5. **Metric boundary:** small-cell, eligibility, evidence, and freshness rules
   constrain what is published.

No application permission can compensate for an over-privileged database
credential.

For the new search/share sources, the safe contract is to exclude search text,
share keys, recipient IP, recipient user agent, and external recipient keys at
EL. Keep polymorphic <code>target_no</code> out of general marts until its
per-share-type PII and FK semantics are approved. Existing landed prohibited
columns require a separate reviewed cleanup migration; adding
<code>exclude_columns</code> does not drop old landing columns.

The HMAC helper in <code>src/utils/crypto.py</code> is not applied on the COPY
path. Do not imply that raw source keys are already pseudonymized.

## Current site

The 2026-08-21 extraction baseline contains 437 SiBC cohort users: 393 currently
mapped to Ulsan and 44 to Jeju. Every cohort user currently has exactly one
approved active site.

This is current state, not history. Known in-place source updates erased prior
site values and did not record the real switch time. Therefore:

- name the attribute <code>current_site_id</code> or expose it through
  <code>bridge_user_site_current</code>;
- test exactly one approved current site per current cohort user;
- never attach current site to an older event as its event-time site;
- do not build a temporal site bridge until upstream change-time and write
  contracts exist;
- do not put site into the <code>user × day</code> grain.

The approved deployment customers are Ulsan
<code>2e0a3387-7058-4f9e-a134-2017f7b7000b</code> and Jeju
<code>778d4ff7-ab76-4070-a9a9-716fac93d9c9</code>. Other iCHMS customers are
application tenants, not deployment sites.

## Connections

| Source system | Database | Airflow connection id |
|---|---|---|
| iccoli | <code>iccoli</code>, schema <code>public</code> | <code>iccoli_db_conn</code> |
| ichms, sibc, irs, discovery | <code>invites_loop</code> | <code>invites_loop_db_conn</code> |
| warehouse | <code>invites_dw</code> | <code>olap_db_conn</code> |

Local environment variables are set by <code>setup_env.sh</code>. Source and
warehouse sessions must agree on timezone because a small number of source
watermarks use naive timestamps. <code>check_timezone_alignment()</code> warns
on mismatch.

## Testing

Tests mirror the package. Database tests use context-managed sessions. Warehouse
tests absorb pipeline commits and roll the session back so real
DDL/COPY/merge behavior can be exercised without leaving rows behind. Preserve
that property.

Use offline tests during P0. Run the full live Python suite only in P6 after the
core graph has passed its storage, freshness, and dbt gates.

Tests must validate dynamic reconciliation rather than pinning volatile row
counts. A changing count is not itself a failure when a source legitimately
backfills; an unexplained difference in grain or reconciliation is.

## Repository conventions

- Existing Python source uses tab indentation; match the file being edited.
- Validate interpolated SQL identifiers with <code>quote_ident()</code>.
- Bind values with <code>%s</code>; COPY bounds use
  <code>cursor.mogrify()</code>.
- Airflow 3 imports come from <code>airflow.sdk</code>, not deprecated
  <code>airflow.decorators</code>.
- Airflow is pinned in the dev dependency group to match its runtime.
- Do not add pandas, Polars, or PyArrow to the streaming EL path.
- No linter or CI is currently configured.
- Generate dbt documentation only after the relevant graph is green:
  <code>uv run dbt docs generate --project-dir dbt --static</code>, then open
  <code>dbt/target/static_index.html</code>.
- Use [HOWTO.md](HOWTO.md) for safe model, metric, access, and Superset
  procedures.
- Use [HANDOVER.md](HANDOVER.md) for owner decisions and operational readiness.
- Keep <code>docs/</code>, <code>data/</code>, and <code>analysis/</code> ignored and
  non-authoritative. Do not make tracked models or documents depend on paths in
  that local archive.
