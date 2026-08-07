# TODO — pick up here

Last updated: **2026-08-07**. Architecture in `CLAUDE.md`; decisions in
`INVITES_LOOP_BI_DECISION_LOG.md`; what measurement overrode in
`IMPLEMENTATION_PLAN.md` §3; handover state in `HANDOVER.md`.

> Replaces the 2026-07-30 version, which predated the transform layer (it still
> described dbt as undecided and the OLAP schema as not started). Recoverable
> in git if any of that context is wanted.

## Where we are

**All five phases are done and committed.** `dbt build` **211/211**, `pytest`
117/117. Extract → load → transform → marts → metric views → Metabase all run
**when invoked by hand**. Nothing runs unattended — see §3.

| Piece | State |
|---|---|
| `extract/`, `load/`, `pipeline.py` | done |
| dbt staging (12 views, allow-list + drift test) | done |
| dbt marts — 6 dims, 5 facts, grain + FK tests | done |
| Metric views — 7 `v_pi_*` + `v_bridge_pi_to_kpi` | done |
| Metabase v0.63.5 + `bi_reader` + 3 dashboards | done, local |
| Metabase FK metadata (14 cols) | done 2026-08-07, pushed from dbt |
| **`fct_user_day` as a behavioural panel** | **done 2026-08-07 — dense spine, 74,410 rows** |
| PII inventory (Q-11) + cleanup | done; R-7/R-8 open |
| 5 ELT DAGs + `transform_dbt_build` | **written; never run on a schedule** |
| **BI viewer choice** | **reopened 2026-08-07 — see Frame 4** |
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

**No GUI BI tool does any of that** — not Metabase, Superset, Lightdash or
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

### Frame 4 — The viewer decision is reopened, and two rejections were wrong

`INVITES_LOOP_BI_DECISION_LOG.md` §4.1 rejected Superset and Lightdash. Both
reasons have failed:

- **Superset — the stated reason is factually wrong.** The log says "four
  moving parts: Redis, Celery workers, metadata DB, `superset_config.py`".
  Redis and Celery are **not required**; they buy async queries, chart caching,
  alerts/reports and thumbnails. Run synchronously and it is two containers —
  parity with Metabase. Corrected in the log.
- **Lightdash — the disqualifier expired.** The log rejected it because it
  "requires a dbt project as an absolute dependency (**none exists today**)".
  One exists now. The log also called it "**best governance fit of the four,
  wrong constraint**"; the constraint changed, the fit did not.

Still rejected, more firmly: **Redash** (SQL-only, structurally contradicts
D-17; maintenance mode) and **Grafana** (observability tool — panel-per-query,
no semantic layer, no ad-hoc multi-dimensional exploration).

What actually separates the candidates now:

| Axis | Metabase OSS | Lightdash | Superset |
|---|---|---|---|
| Non-dev GUI authoring | best | good | weakest |
| Implicit FK joins | **yes** (built 2026-08-07) | dbt-defined | no — dataset-bound |
| Dashboards as code | **no** (Pro only) | yes | yes (YAML) |
| Row-level security | **no** (Pro only) | — verify | yes, free |
| Audit logs | **no** (Pro only) | — verify | — |
| Compliance upgrade path in-org | Pro | **SOC 2 / HIPAA / BAA** | none (vendor: Preset) |
| Korean locale | solid (`ko`) | **verify** | **verify — likely partial** |
| MCP | yes | **no on OSS** | — |

The MCP gap matters less than it looks: agents already reach the warehouse
directly via the `invites-loop-olap-connection` skill, and this session's
finding was that Metabase MCP does **not** block write tools, which is a
liability as much as a feature.

**Triggers that would force the switch:** a second deployment site needing
row-level restriction (`dim_deployment_site` exists, `KR_LOOP_PILOT` is a
placeholder), or an audit-logging requirement for clinical/genomic data.

**Recommended next step, not yet done:** spike Lightdash against the same
acceptance test used for Metabase — filter `fct_user_disease_day` by
`dim_disease.phenotype_kor` **and** `dim_user.sex` without SQL — and check
Korean UI coverage. Do it *after* the marts work, per Frame 1.

---

## Done 2026-08-07

### 1. dbt-metabase FK sync — DONE

Metabase now carries **14 of 14** FK columns (was 0 of 21). Pushed with
`dbt-metabase models`, which infers them from the native dbt `relationships`
tests already declared in `marts.yml` — so the FK graph ships from git.

The `422 — Timed out after 10.0 s` on the pre-flight `sync_schema` was exactly
what we thought: off-network, Metabase could not reach the Azure warehouse.
On-network it succeeded first try, no `--sync-timeout 0` needed.

**Acceptance test passed.** Question on `fct_user_disease_day` broken out by
`dim_disease.phenotype_kor` *and* `dim_user.sex`, no SQL: 68 rows, headers
rendered as `Disease → Phenotype Kor` (Metabase's implicit-join notation, which
only appears when the FK graph is live).

Command, verification and the manual fallback are in `HOWTO.md` §3 Option A.
Re-run it after any marts change. The API key used was deleted afterwards;
the instance again has none.

Minor thing to glance at, not a defect: every phenotype returns identical counts
(2496 F / 2052 M), consistent with `fct_user_disease_day` carrying a row per
user-day for *all* scored phenotypes. Worth confirming that is the intended
grain.

### 2. `HOWTO.md` §3 Option A rewrite — DONE

Leads with dbt-metabase; manual UI/API route kept as an explicit fallback; the
14-row mapping table retained as a statement of what should exist, with a note
that `marts.yml` wins if the two disagree. §2 Step 5 now points at the same
command instead of the UI. API examples switched from `X-Metabase-Session` to
`x-api-key`.

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
| Wearable users @ 2026-07-31 | 167 | **177 — UNRECONCILED** |

The dominant-variable finding reproduces. The low buckets read lower than the
document because this pools completions/deliveries where the source averaged
per-user rates, and because the dense spine adds zero-activity months to the
denominator — the denominator effect itself. **The two are not directly
comparable; do not quote them side by side.**

---

## Start here next session

In order. The first three continue Frame 2 and are pure code; the fourth is the
viewer spike from Frame 4 and should wait until they land.

### A. Reconcile the wearable count — 177 vs the documented 167

Same cutoff date (2026-07-31), ten users apart. Two candidate causes, neither
checked: **cohort scope** (§1 worked from the 442 LOOP-mapped set, `dim_user`
is the 404 sibc cohort) or a **stream-filter difference** in what counts as a
firing. Until this closes, `wearable_streams_active` should not be quoted
against C3's 167. Meal reconciles exactly, so the join path itself is sound.

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

### C. Re-push metadata to Metabase

`fct_user_day` gained ~11 columns that Metabase has never seen, and their
descriptions carry the denominator and control-variable warnings. Needs a fresh
admin API key and one `dbt-metabase` run — `HOWTO.md` §3 Option A. Delete the
key afterwards.

### D. Then, and only then, spike Lightdash

Per Frame 1 and Frame 4. Acceptance test and open questions are in Frame 4.

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

### 4. MCP restriction posture

Tested today with group-scoped API keys:

- **Tool visibility is not a permission boundary** — a Planning Team key sees
  all 15 tools, `execute_sql` included.
- **Group permissions enforce** — Planning Team → `execute_sql` is refused
  (*"You do not have permission to run native queries against this database"*).
  **D-17 survives MCP.**
- **`bi_reader` enforces even for admins** — an admin key hitting
  `stg_sibc.chat_msgs` got `permission denied for schema stg_sibc`. **D-16
  holds through a second access path.**
- **Write tools are NOT blocked** — a Planning Team key created a collection
  (probe archived). Same authority as in the browser, now reachable by an agent
  acting on a loose instruction.

Decide: set `mcp-execute-sql-enabled: false` (kills raw SQL over MCP
instance-wide, including admins)? Restrict write scopes? Note it is
**unverified** whether an admin can cap the grantable scope set per client —
test before relying on scopes as enforcement. Detail in `HOWTO.md` §1.

### 5. dbt-metabase dependency — DONE

Committed as `d3dd7fb` (`dbt-metabase>=1.7.5` in the `transform` group). The
tool is now proven here; see §1.

### 6. Carried-forward open items

| Item | State |
|---|---|
| **Q-04 permanent owner** | Deferred; ACH interim. The one deliverable code cannot close |
| `MB_ENCRYPTION_SECRET_KEY` | Only in local `.env` — needs a password manager / Key Vault |
| Deployment site code | `KR_LOOP_PILOT` is a placeholder; confirm before it labels a dashboard |
| Glucose units | Normalised by threshold; a per-row unit from Discovery would retire the heuristic |
| ichms table scope | Identifier columns dropped, but no mart reads these tables at all |
| PII inventory R-7 / R-8 | Discovery clinical payload tables; re-run inventory on target changes |
| Unmapped cohort users | 2 active members with no iccoli link — owner follow-up |
| Metabase upgrade cadence | v0.63 EOL **2026-09-07**; non-LTS gets ~2 months. Put it on a calendar |
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

## Test artefacts left in place

- `planner.test@invites.local` — All Users + Planning Team, not superuser,
  password in the session scratchpad (ephemeral). Kept for permission testing;
  delete via Admin → People when done.
- MCP server registered with Claude Code at **local scope**
  (`~/.claude.json`, this project only), OAuth authorised as admin. MCP tools
  load at session start — start a fresh session to use them.
- All test API keys deleted; probe collection archived. The admin key minted
  2026-08-07 for the FK sync was deleted immediately after (verified: the API
  now returns 401). No API keys currently exist in the instance.
- Local stack sizing changed 2026-08-07: Colima VM 4 CPU / 8 GiB → **2 CPU /
  4 GiB**, and `JAVA_OPTS` 3g → **2g** in both `.env` and `docker-compose.yml`
  in `invites-loop-bi-deploy` (uncommitted there; `.env.bak.20260807` kept).
  The heap cap had to come down with the VM — `-Xmx3g` inside a 4 GiB VM is the
  documented exit-137 trap. Measured after: 1.26 GiB of 3.81 GiB, 0 restarts.
- Last verified backup restore: 2026-08-06 post-upgrade — 178 tables,
  5 dashboards, 11 questions, 5 permission groups into a scratch container.
