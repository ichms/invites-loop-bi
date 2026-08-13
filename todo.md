# TODO — pick up here

Last updated: **2026-08-13**. Architecture in `CLAUDE.md`; decisions in
`INVITES_LOOP_BI_DECISION_LOG.md`; what measurement overrode in
`IMPLEMENTATION_PLAN.md` §3; handover state in `HANDOVER.md`.

> Replaces the 2026-07-30 version, which predated the transform layer (it still
> described dbt as undecided and the OLAP schema as not started). Recoverable
> in git if any of that context is wanted.

## Where we are

**All five phases are done and committed.** `dbt build` **388/388**, `pytest`
**125/125**. Extract → load → transform → marts → metric views → Superset all run
**when invoked by hand**. Nothing runs unattended — see §3.

| Piece | State |
|---|---|
| `extract/`, `load/`, `pipeline.py` | done |
| dbt staging (12 views, allow-list + drift test) | done |
| dbt marts — 6 dims, 5 facts, grain + FK tests | done |
| Metric views — 7 `v_pi_*` + `v_bridge_pi_to_kpi` | done |
| Superset 6.1.0 + `superset_reader` (`deploy/superset/`) | done 2026-08-11, local |
| Superset datasets (19 marts relations) + PI dashboard as code | done 2026-08-11, scripted |
| **`fct_user_day` as a behavioural panel** | **done 2026-08-07 — dense spine; 76,026 rows @ 08-10** |
| Wearable retroactive-data loss (A′) | **found + fixed + backfilled 2026-08-10** |
| PII inventory (Q-11) + cleanup | done; R-7/R-8 open |
| 5 ELT DAGs + `transform_dbt_build` | **written; never run on a schedule** |
| Superset Planning-Team role + backup drill | **open — see HANDOVER.md** |
| **Named owner (Q-04)** | **deferred — interim only** |

---

## The frames we now work under

Four framings changed on 2026-08-07. They are recorded here because they
reorder the remaining work, and because each corrects something previously
written down as settled.

### Frame 1 — The mart is the deliverable; the viewer is the cheap layer

The analytical bar for this project is set by work already done in
`analysis/` and `~/AgentWorkspaces/invites_loop/bi`: Spearman rank
correlation, Mann-Whitney U, and **OLS with covariate control**.

**No GUI BI tool does any of that** — not Superset, Lightdash or
Grafana. So analytical depth **cannot discriminate between viewers**. It is a
requirement on the *warehouse*, which is what decision-log line 39 said all
along: the semantic layer lives in PostgreSQL and git, not inside the BI tool.

Consequence for sequencing: **make the marts analysis-ready first, choose the
viewer second.** Choosing the viewer first optimises the layer we already
decided is disposable (D-19: rebuilding three dashboards is half a day).

### Frame 2 — Design for the operations, not for the request

Measured on 2026-08-07: the point-mission notebook reads `stg_iccoli` (32
refs), `stg_sibc` (9), `stg_discovery` (1) and **`marts` zero times**. The
star schema served the viewer and nothing else. Porting that one notebook
would have fixed exactly one notebook.

The five verification rounds in `DASHBOARD_METRIC_FEEDBACK.md` are not five
questions. They are the **same seven operations** applied to different
channels:

| Operation | Demands of the mart |
|---|---|
| Relative-time cohorting (M0–M7, not calendar) | `months_since_joined` |
| Denominator declaration | numerator **and** denominator as paired columns |
| Control for app access days | `app_login_events` as a first-class column |
| Negative control | parallel channels at identical grain |
| Within-person deviation | user × period panel with history to centre on |
| Segment moderation | conformed age / sex / BMI bands |
| Observability flags | who is even observable per channel |

Build for those seven and the next request is a query, not a project.

### Frame 3 — Zero days are the denominator

A behavioural rate needs the days a user did nothing. Aggregating over a spine
of only-active days divides by the wrong number and biases every rate upward.

This is not theoretical here. `DASHBOARD_METRIC_FEEDBACK.md` §5.2 records a
published *"dietary logging is 미흡"* verdict that was a pure denominator
artifact — per-recorder intensity had **risen** 6.2 → 21.1 days/month. The
verdict reversed once the denominator was stated.

So: any fact backing behavioural analysis is dense by default, and the
reconciliation test is not optional (see §7).

### Frame 4 — The viewer is settled (Superset, D-11); what would reopen it

The choice was made on the axes that actually discriminate — not analytical
depth, which Frame 1 already ruled out as a differentiator:

- **Content as code.** The warehouse connection, all 19 datasets, and the PI
  dashboard are created by scripts in `deploy/superset/`. A rebuilt instance
  is three commands from whole. This is the property the semantic-layer
  principle (log line 39) wants from the viewer, and Superset gives it free.
- **Row-level security exists, free**, for the day a second deployment site
  needs row restriction (`dim_deployment_site` now contains the approved Ulsan
  and Jeju source rows).
- **The cost, named:** no implicit joins — every chart reads one dataset, so
  cross-table questions need pre-joined wide models (`HOWTO.md` §3), and
  Planning-Team GUI authoring is weaker than the alternatives. Korean UI
  coverage (`BABEL_DEFAULT_LOCALE = ko`) is enabled but not yet exercised by a
  real Planning-Team user.

Still rejected, firmly: **Redash** (SQL-only, structurally contradicts D-17;
maintenance mode) and **Grafana** (observability tool — panel-per-query, no
semantic layer, no ad-hoc multi-dimensional exploration). The full rejection
table is the log's §4.1.

**Triggers that would reopen the choice:** the Planning Team failing to
self-serve after the wide datasets and Korean UI land (Lightdash is the
fallback — best governance fit, metric definitions as dbt YAML, and a
commercial SOC 2 / HIPAA / BAA path that answers the Q-04 orphan risk), or an
audit-logging requirement for clinical/genomic data. The acceptance test for
any candidate: filter `fct_user_disease_day` by `dim_disease.phenotype_kor`
**and** `dim_user.sex` without SQL, in Korean.

---

## Done 2026-08-11

### 1. Superset deployed, datasets registered, PI dashboard as code — DONE

`deploy/superset/`: pinned 6.1.0 (one-line Dockerfile adds the missing
psycopg2 driver), `postgres:17` app DB on a named volume, one-shot idempotent
init (migrate → admin → warehouse connection via `set-database-uri`).
`superset_reader` created and verified marts-only with KST at the role;
all 19 marts relations registered as datasets
(`scripts/register_marts_datasets.sh`); the PI dashboard — 8 charts, layout,
and the METRICS.ko.md interpretation rules as an on-dashboard card — built by
`scripts/build_pi_dashboard.py` and verified through the chart-data API
(every query returns rows; SQL Lab shows `now()` at `+09`).

Two findings worth keeping: SQL Lab ships a function denylist
(`current_setting`, `version`, `pg_sleep`, … all blocked by default), and the
one row-count worth spot-checking rendered right — `fct_user_day` 76,026.

### 2. `HOWTO.md` rewritten around the dataset model — DONE

§1 now covers AI-client restriction in terms of the DB role (the layer that
enforces) vs Superset app roles (which do not protect data); §2 Step 5 is
dataset registration; §3 explains the one-chart-one-dataset rule, keeps the
14-row join map from `marts.yml` as the statement of legal joins, and orders
the options: pre-join in dbt → virtual dataset → SQL Lab.

## Done 2026-08-07

### 7. `fct_user_day` is now a behavioural panel — DONE

Frames 2 and 3 made concrete. `dbt build` 184 → **211/211**.

**Spine: sparse → dense.** 5,747 → **74,410 rows**. Was the union of
IRS-scoring and integrated-analysis days — 9.3% of the user-days the cohort
actually lived. Now every day from the earlier of enrolment and first observed
activity, to the observation frontier.

Two design points worth not re-deriving:

- **Frontier, not `current_date`.** The upper bound is the last day any
  behavioural source actually delivered. Extending to today manufactures
  zero-activity days for dates the ELT has not loaded, and a flat line of false
  zeros at the right edge reads as a product collapse. Per-channel lag is *not*
  modelled — check `dbt source freshness` before reading the last few days.
- **Spine starts before enrolment where activity did.** `joined_dt` is entry to
  the sibc study cohort; app usage predates it for some users. It also gives
  §1.3 the pre-period its ownership-transfer natural experiment needs.

**New columns:** `days_since_joined` / `months_since_joined`,
`app_login_events` + `did_login`, `routines_delivered` / `routines_completed`
(denominator pair), `manual_measurements`, `meal_records`,
`wearable_streams_active`, `app_actions`, `active_input_events` /
`had_passive_collection`.

**New staging models:** `stg_discovery__lifelog_meal` (the C22 channel — the
dashboard had `disc_lifelog_user_food` at 11 users while the real one carries
335) and `stg_discovery__lifelog_wearable_day` (union of all five streams per
C3; materialised as a **table** because heartrate is ~8.5M rows).

**A defect found by reconciliation, not by tests.** The first spine started at
`joined_dt` and silently dropped **381 meal records and 23 of 335 recorders**.
Everything built; every grain and `not_null` test passed. It surfaced only when
totals were compared against source. Hence
`dbt/tests/assert_user_day_spine_loses_no_activity.sql`, which asserts fact
totals equal staging totals per channel — that test is what makes the spine
bounds safe to change. **Do not delete it when editing the spine.**

**Validation:**

| Check | Documented | Panel |
|---|---|---|
| Meal users / records | 335 | **335 / 37,374 — exact, zero loss** |
| §4.5 routine completion @ 16+ login days | 65–72% | **71.6%** |
| §4.5 gradient across buckets | ~3× | 7.0% → 22.4% → **71.6%** |
| Wearable users @ 2026-07-31 | 167 | 177 → **181 after the 08-10 backfill; reconciled, panel is right** |

The dominant-variable finding reproduces. The low buckets read lower than the
document because this pools completions/deliveries where the source averaged
per-user rates, and because the dense spine adds zero-activity months to the
denominator — the denominator effect itself. **The two are not directly
comparable; do not quote them side by side.**

---

## Done 2026-08-10

### A. Wearable count reconciled — the panel's 177 is correct

The documented 167 is **a stale snapshot, not a target**. Same union, same
cutoff; the difference is extraction date, because this data grows backwards.

**Proof by monotonicity, which needs no reconstruction of the old query.** C3
worked over the ~442 LOOP-mapped set; `dim_user` is 404, of which **402 are
inside that mapped set** (the other 2 are the known unmapped pair below). Same
definition and same cutoff over a *superset* of users must yield a count ≥ ours.
The doc got 167 against our 177. At most 2 users can be blamed on scope, so ≥8
of the gap cannot be — the data itself differs.

Confirmed directly: at 2026-07-31 the count rises monotonically with how
recently the data was pulled — **167** (doc) → **177** (panel, in-cohort) →
**181** (our staging, unrestricted) → **185** (source today, step alone).

Both candidate causes in the old item A were wrong. It is not **cohort scope** —
that pushes the count *down* by 4, the wrong direction. It is not a
**stream-filter difference** — C3's 167 is the same five-way union this model
already implements. The real cause is the retroactive backfill in **A′**, which
is why closing A opened a defect instead.

**Consequence:** `wearable_streams_active` is sound and can be used. But no
wearable count is a constant — always quote it with its extraction date. Do not
"fix" the model to reproduce 167.

**Worth an owner decision, separately:** step alone determines the union — every
user with any stream has step (186 of 186 unrestricted; zero exceptions). 44
in-cohort users have step and *nothing else*, at well under half the day-density
(median 38 wear days vs 95). Phones count steps without a watch and nothing in
the data separates them. So "has a device" means "has step data", and that
choice is the entire distance between **181** and **137** (union excluding
step). Recorded in the model header.

### A′. Wearable retroactive-data loss — found, fixed, backfilled

Closing A did not close cleanly; it exposed a live pipeline defect.

**The defect.** All five wearable streams watermark on the **measurement** time
(`measured_dt`, `total_measure_end_dt`). Wearables sync late, so a watch uploads
samples stamped days or weeks earlier. Those rows land *below* the watermark,
where `measured_dt > last_watermark` can never see them. Not lag — permanent,
silent loss. **No source table carries an insert timestamp** (checked), so
watermarking on arrival time was not an option.

`step` gave the clean measurement, its 2026-08-06 load being a single full read:
**454 rows for dates ≤ 08-06 arrived after it**, reaching **29 days back**,
decaying with age (75 on the load date, ~12–15/day for three weeks, 1–3 at
26–29 days). Hence a 30-day window — measured, not guessed.

**The fix.** New per-table `lookback_days` in the target config, wired through
`build_extractor` as the extractor's existing `overlap`. Declared 30 days on
step / activity / sleep / SpO₂. Correctness is free: those tables are already in
`KNOWN_MISSING_PRIMARY_KEY`, so the loader does delete-window-then-insert, and
the delete window is built from the same widened bound — a test pins that.
An operator's `--overlap-minutes` can widen a declared lookback but never narrow
it. **Heartrate deliberately excluded**: 8.5M rows, no usable index, and step is
a strict superset of the wearable user set, so it recovers nobody.

**Backfilled and verified.** Ran the four streams; at the 2026-07-31 cutoff the
warehouse now equals the source exactly — step 186/186, activity 135/135, sleep
123/123, SpO₂ 119/119. Heartrate remains 133 vs 135, by design. `dbt build`
**211/211**, `pytest` **125/125** (8 new). `fct_user_day` 74,410 → **76,026**
rows, frontier now 2026-08-10, wearable users at 07-31 **177 → 181**.

**The trap this ran into, now documented in the config.** Loading a lifelog
child without its parent orphans rows *silently*. Refreshing four streams to
08-10 against a `disc_lifelog_user_info` frozen at 08-06 left **4,651
unattributable step rows** and drove the wearable count **down to 169 while the
row count went up** — every dbt test still green, because an unmatched
`user_lifelog_sn` is dropped by an inner join, not flagged. A whole-system run
is safe; a hand-run `--table` on any child needs the parent run straight after.
A per-channel source-vs-warehouse count is the only thing that catches it.

---

## Start here next session

> **Data-transfer freeze lifted 2026-08-13** (owner). The 2026-08-10 hold was
> the Jeju registration-error window. Loads may run again. Zone *modelling*
> is still out of scope until the dev-team answers in `CLAUDE.md` land —
> lifting the freeze is not permission to invent affiliation semantics.

In order. **A and A′ both closed 2026-08-10.** Heart-rate lookback and
`fct_wearable_day` are the 2026-08-13 follow-on (intensity, not presence).
Item B (`dim_user` segments) is in the working tree; B0 zone work stays
blocked.

### Wearable intensity — `fct_wearable_day`

Presence (`wearable_streams_active` on `fct_user_day`) does not carry step
counts, sleep hours, SpO2 or heart-rate values. Those stay out of
`fct_measurement` (wrong grain). The daily fact is sparse: NULL means the
stream did not fire, not zero. Heart rate now has the same 30-day
`lookback_days` as the other four streams.

### Wearable observations — six source-shaped facts

Added 2026-08-13 for observation-level analysis without contaminating
`fct_measurement`. Point samples, intervals and sleep sessions do not share one
honest grain, so they stay in `fct_wearable_step`, `fct_wearable_activity`,
`fct_wearable_heartrate`, `fct_wearable_oxygen_saturation`,
`fct_wearable_sleep` and `fct_wearable_sleep_stage`. Exact duplicate payloads
collapse to one observation and retain their multiplicity in
`source_row_count`; attribution and count reconciliation are build failures.

At the 2026-08-13 14:51 KST extraction, the cohort facts contain 19,080 step,
14,061 activity, 8,877,550 heart-rate, 60,867 SpO2, 10,314 sleep-session and
614,708 sleep-stage distinct observations. The targeted lineage is **190/190**
and the current full `dbt build` is **388/388** green. These are extraction-dated
readings, not constants.

Resume load (do not start EL over): whole-system runs, heart-rate lookback
on `measured_dt`, iccoli watermark delete (enrolment wave), `auth_user_customer`
full-refresh. Then `dbt build`.

### B0. Site affiliation is multi-valued — do this before B

Owner raised 2026-08-10: *"this person was in Ulsan and is now also in Jeju"* —
one person, two affiliations, one field.

The full analysis is in `CLAUDE.md` § "Site affiliation is multi-valued". The
headline is that the constraint is **ours, not the source's**:
`ichms.auth_user_customer` is already a temporal bridge (surrogate PK, no unique
on `user_id`, `linked_dt` / `unlinked_dt`), both tables are **already landed in
`stg_ichms`**. At the 2026-08-10 measurement all 404 `dim_user` users resolved
to ULSAN, while `dim_user.site_id` was a hardcoded `'KR_LOOP_PILOT'` literal.
That state is superseded by the 2026-08-13 update below.

**It sequences before B** because B adds "cohort group — Ulsan participant vs
internal staff", which is *the same axis*. Building that as a single-valued
column and then discovering affiliation is many-to-many means tearing it out.
Decide the cardinality once, then build both on it.

Open owner questions at that point, none of which code could settle: which
`auth_customer` rows are sites rather than app tenants; whether overlapping
active links mean "moved" or "both" (only 10 of 1,113 rows ever set
`unlinked_dt`); and the reporting rule for a dual-affiliated user's facts.

**Update 2026-08-12 — B0 is now blocked on the dev team, not just the owner.**
The Jeju launch (2026-08-10) was handled by manually re-pointing 13 staff rows
in production — an in-place `customer_id` UPDATE that left no history and is
invisible to the `linked_dt` watermark — and the application turns out to
enforce user:customer 1:1 at code level, so the schema's multi-valued
capability is not backed by any write path. "Moved vs both" is thereby answered
*for staff* (exclusive switching, by app constraint), but the switch times are
unrecorded. Full findings and the seven-item request to the dev team are in
`CLAUDE.md` § "Site affiliation is multi-valued", update of 2026-08-12. At that
point the rule was **build nothing zone-aware** (superseded for current-site
filtering by the update below), and note for item B: the
staff-vs-participant column must come from an owner-provided roster, never from
`auth_user_customer` traces — two confirmed staff accounts are new hires with
no Ulsan history at all.

**Update 2026-08-13 — current-site reporting is enabled; history is not.**
Owner-approved site IDs are Ulsan
`2e0a3387-7058-4f9e-a134-2017f7b7000b` and Jeju
`778d4ff7-ab76-4070-a9a9-716fac93d9c9`, excluding every application tenant.
`dim_deployment_site` now reads those two rows and `dim_user.site_id` reads the
one active approved link. All 416 cohort users currently have exactly one
(392 Ulsan, 24 Jeju). This permits a current-site filter only. Historical/as-of
site metrics, a temporal bridge and simultaneous dual-affiliation semantics
remain blocked because in-place source flips erase the prior site and switch
time.

### B. Extend `dim_user` — the segment attributes Frame 2 needs

Still missing, and §1/§2 both turn on them:

- **`weight` / `height` / `bmi_band`** — `sibc.user_master` has them complete
  for all 403 (§2.1 measured zero missing). §2.5 warns BMI is non-monotonic and
  confounded with age, so band it and never interpret it alone.
- **Cohort group — Ulsan participant vs internal staff.** §1's entire result is
  this 392 / 50 split, and it is representable nowhere today. Note §1.5's
  caveat: 29 of the 50 staff have accounts only, so the contrast is
  "participation contract vs none", **not** "voluntary vs involuntary". Whatever
  the column is called, that distinction must survive into its description.
- **Per-user observability flags per channel** — §2.4's structural finding
  (wearable ownership and routine completion run *inverse* across age; only 98
  users have both) is uncomputable without them.

### C. Push column descriptions into the Superset datasets

The dbt descriptions on `fct_user_day`'s panel columns carry the denominator
and control-variable warnings. `dim_user.site_id` now carries a different
load-bearing warning: it is a real **current-site** segment, but not historical
affiliation. A non-SQL user can filter today's Ulsan/Jeju population with it;
grouping past events by it silently reattributes those events after a move.

Superset dataset columns have a `description` field settable over the REST
API, but nothing ships the dbt manifest into it — extend
`register_marts_datasets.sh` (or a sibling script) to read
`dbt/target/manifest.json` and PUT column descriptions per dataset.
Alternative: configure dbt `persist_docs` so descriptions land as database
comments, which Superset reads on dataset sync. Either way the source of
truth stays the dbt YAML.

---

## Blocked — needs an owner decision, not code

### 3. Nothing is actually scheduled

Checked 2026-08-07. The DAGs are written and committed, but **no scheduled run
has ever occurred, and none can**:

- No Airflow scheduler process is running, and none is deployed anywhere.
- The metadata DB (`~/airflow/airflow.db`, SQLite) has not been written since
  **2026-07-30 17:18**.
- All five ELT DAGs are **paused** (`is_paused=1`).
- `transform_dbt_build` is **not registered at all** — added in `e537c25`, after
  the last DAG-parse, so Airflow has never seen it.
- Total DAG-run history: one manual `elt_irs_to_staging` on 2026-07-30.

So `schedule="0 1 * * *"` in `elt_to_staging.py:39` is a declaration, not a
behaviour. Every load and `dbt build` so far has been a manual CLI invocation,
and the marts are only as fresh as the last time someone ran one.

This is **Q-13 (production hosting) arriving early** — it was deferred on the
grounds that everything is hosting-independent, which remains true, but the
consequence is that unattended operation does not exist. Decide the target
(a always-on host? managed Airflow? cron calling the CLI?) before treating any
dashboard number as current.

Cheap interim if a decision is not imminent: run the scheduler locally and
unpause, accepting that it only runs when the laptop is awake and on-network.
Better than the current state mainly because failures become visible.

---

## Owner decisions (no network needed)

### 4. AI-client and Planning-Team access posture

Two related decisions, detail in `HOWTO.md` §1:

- **AI clients:** the enforcing layer is the DB role — an MCP Postgres
  connector gets marts-only read credentials (`superset_reader`'s grants),
  never `analytics_user`. Decide whether agents may hold a Superset login at
  all; an Admin session can register new warehouse connections, which makes
  it equivalent to whatever credentials the admin can type.
- **Planning Team:** configure the dashboards-only Superset role (Gamma
  minus SQL Lab) so D-17 is enforced in the app as well as at the role.
  Until then every Superset login can open SQL Lab; `superset_reader` still
  caps what that reads.

### 6. Carried-forward open items

| Item | State |
|---|---|
| **Q-04 permanent owner** | Deferred; ACH interim. The one deliverable code cannot close |
| `SUPERSET_SECRET_KEY` + `superset_reader` password | Only in local `deploy/superset/.env` — needs a password manager / Key Vault |
| Historical site attribution | Current Ulsan/Jeju is available; source flips erase prior site and switch time, so as-of reporting remains blocked |
| Glucose units | Normalised by threshold; a per-row unit from Discovery would retire the heuristic |
| ichms table scope | Identifier columns dropped, but no mart reads these tables at all |
| PII inventory R-7 / R-8 | Discovery clinical payload tables; re-run inventory on target changes |
| Unmapped cohort users | 2 active members with no iccoli link — owner follow-up |
| Superset upgrade cadence | Pinned `6.1.0` in the deploy Dockerfile; check releases quarterly, back up before bumping |
| Q-03 existing BI tool | Never answered; would only have changed Phase 4 |
| Q-13 production hosting | No longer harmless to defer — it is what blocks §3 (nothing is scheduled) |

---

## Known deferrals (carried from the previous plan, still valid)

- **Hard deletes never arrive.** Watermark extraction cannot see a deleted row.
  `tb_ext_user_mapper` was moved to full-refresh for exactly this reason
  (a deleted mapping silently corrupted cohort membership). The general case is
  unaddressed: classify remaining tables as append-only vs mutable-without-
  marker, and decide the deletion-request path (given a purged upstream user,
  remove their rows from `stg_*` and the marts by user key).
- **`utils/crypto.py:generate_user_key()` is still unused.** Pseudonymisation
  was solved differently — direct identifiers are excluded at the EL boundary
  (N-01) rather than hashed. Either wire it up or delete it; a helper that
  looks like policy but runs nowhere is worse than neither.
- **Batched loading (by bytes, not rows).** Not needed at current volumes, but
  the design is understood: loop over watermark windows with a byte budget,
  each window a full extract→load→commit (`run_table()` already takes
  `upper_bound`). Row counts are the wrong unit — row widths span ~112 B to
  ~653 kB across these sources.
- **No usable index on watermark columns of the big discovery tables.**
  `disc_lifelog_user_heartrate.measured_dt` only appears inside a composite;
  each incremental run seq-scans. Tolerable at current size, and it is a change
  to a production source DB — monitor rather than act.
- **15 incremental targets have no primary key** (2 sibc, 13 discovery lifelog
  — `disc_lifelog_user_step` joined the list today). Accepted: the loader uses
  delete-window-then-insert, which is idempotent. Pinned in
  `KNOWN_MISSING_PRIMARY_KEY`.
- **No linter or CI.**
- **`apache-airflow` pinned `~=3.2.2`** to match the local install; bump
  alongside the deployed image.

---

## Local state worth knowing

- Superset stack running on **:8088** (Colima VM: 2 CPU / 4 GiB). Admin login
  is `admin`; its password, the app-DB password, `SUPERSET_SECRET_KEY` and the
  `superset_reader` warehouse password are all in `deploy/superset/.env`
  (gitignored, generated). Move the lot to the password manager — see §6.
- The only Superset content is what the scripts create: 19 datasets and the
  `pi-metrics` dashboard. No API keys, no extra users, no UI-only content —
  the app DB is currently reproducible from git, which makes this the cheapest
  moment to do the backup/restore drill (HANDOVER.md #4).
