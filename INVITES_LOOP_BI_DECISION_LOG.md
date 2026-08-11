# INVITES_LOOP_BI — Architecture Decision Log

**Version:** v0.3
**Date:** 2026-08-06
**Changes since v0.2:** D-21 (Azure Container Apps) demoted to deferred — production hosting is now Q-13; added D-28 (local-first development); clarified the application-database vs. data-warehouse distinction under D-13; Q-02 marked conditional on the Azure path
**Changes in v0.2:** added §2.5 PII & data minimisation (D-22–D-27); added Q-10 (canonical user key), Q-11 (PII inventory verification), Q-12 (age exposure granularity); sequencing renumbered to §2.6
**Owner:** Changmin Ahn (ACH) → handover to junior data engineer
**Scope:** BI / semantic layer / viewer stack for the Invites Loop OLAP data warehouse (Azure PostgreSQL)

---

## 0. Governing constraint

Every decision in this document is evaluated against one binding constraint, not against feature quality:

> **The system must remain correct and modifiable by a junior data engineer and by non-developer Planning Team members, with the original author absent.**

Two corollaries that drive most of the choices below:

1. **Loud failure beats silent failure.** An unattended system that stops with a test error is safer than one that keeps producing plausible wrong numbers.
2. **Fewer moving parts beats more capability.** Each additional service is an additional thing that can break with nobody qualified to fix it.

---

## 1. Architecture (agreed shape)

```
raw JSONB logs  (sibc.*, iccoli.*, invites_loop.*)
   ↓  dbt Core — staging: flatten JSONB, type, dedupe
stg_*
   ↓  dbt Core — marts: conform, declare grain
dim_* / fct_*                    ← Superset dataset surface; non-devs live here
   ↓  thin SQL views
v_kpi_* / v_pi_* / v_bridge_*    ← canonical metric definitions, git-reviewed
   ↓
Superset (read-only role, marts schema only)
```

**Design principle:** the semantic layer lives in PostgreSQL and git, not inside the BI tool. This makes the viewer choice reversible and keeps metric definitions diffable and reviewable.

---

## 2. DECIDED

### 2.1 Transformation & orchestration

| # | Decision | Rationale |
|---|---|---|
| D-01 | **Transformation is dbt Core** (Apache 2.0, self-hosted CLI) | Free; includes tests, docs, lineage. `dbt test` converts silent grain breakage into a loud build failure — the single highest-value property for an unattended system. |
| D-02 | **Orchestration stays in existing Airflow.** A single `BashOperator` runs `dbt build` at the end of the L DAG | 15 models does not justify task-level granularity. `ref()` handles build order; hand-maintained Airflow task dependencies drift and produce stale-but-plausible numbers. |
| D-03 | **Stay on dbt Core, not Fusion** | Fusion ships under ELv2. Core remains Apache 2.0. Pin the version. |
| D-04 | **Every fact model declares its grain in a header comment and enforces it with a dbt `unique` test on the grain key** | The grain declaration is the contract. This is the artifact that stops a junior from silently wrecking the model. |
| D-05 | **Every JSONB-extracted field gets a `not_null` test plus a custom null-rate threshold test** | The backend schema docs explicitly state `모델/룰 변경으로 키 확장 가능`. The extraction contract is a moving target; a key rename silently produces NULLs and flatlines the dashboard. |

### 2.2 Warehouse modeling

| # | Decision | Rationale |
|---|---|---|
| D-06 | **Star schema: conformed dims + facts with declared grain** | Not a performance argument (403 users; Postgres will not care). Three real reasons: (a) Superset charts read one dataset each, so every chartable relation needs a declared grain, and conformed dims are what make the pre-joined wide datasets derivable in one honest hop; (b) sources are partitioned JSONB logs, so flattening to typed columns is mandatory work regardless; (c) a declared grain is a falsifiable contract. |
| D-07 | **Natural keys, no surrogate keys** — `user_id` (uuid), `ymd`, `disease_id` | Joins on natural keys are writable and debuggable by a junior with nobody to ask; a broken surrogate-key map is a worse outcome than any benefit gained at this scale. Deliberately against textbook Kimball. **Scoped exception:** where two source systems carry competing identifiers for the same entity and neither is canonical, one conformed key must be elected — see Q-10. Electing an existing key is not the same as minting a synthetic one. |
| D-08 | **SCD Type 1 dims only. No Type 2.** Time-varying attributes (device assignment, site, cohort status) go into the fact at event time | SCD2 done wrong produces confidently wrong history and will be done wrong by someone learning it from a blog post. |
| D-09 | **No snowflaking.** Denormalize into the dim | Every construct added is a construct that can break silently and requires expertise to fix. |
| D-10 | **Metric definitions live in thin SQL views over the star**, one view per metric, tier encoded in prefix (`v_kpi_`, `v_pi_`, `v_bridge_`) | Once the star exists, definitions get short. Thin definitions are reviewable definitions — a reviewer can look at six lines and say "that's wrong"; nobody can do that with 80 lines of `->>`. This is what protects the KPI/PI/Bridge separation after departure. |

**Proposed model set** (grain to be confirmed — see Q-01):

| Model | Grain | Source | Note |
|---|---|---|---|
| `fct_user_day` | user × ymd | `sibc.user_irs_log`, `user_intg_log` | Scalar IRS+/LRS/MRS/PRS. Carry the explicit residual term as a column. |
| `fct_user_disease_day` | user × ymd × disease_id | `risk_overview[]` explosion | **Do not collapse into `fct_user_day`** — collapsing loses the 35-condition slice. ~5M rows/yr. |
| `fct_coaching_event` | one JITAI delivery | SiBC | Delivery, response, latency. |
| `fct_measurement` | user × device × ts | device BP/weight | `device_type` as dim FK so the bimodal density problem is sliceable, not a footnote. |
| `fct_app_action` | one action log row | `iccoli.tb_action_user_log` | Engagement. |
| `dim_user` | user | — | Site, cohort, enrollment date, device allocation flag. |
| `dim_date` | date | generated | — |
| `dim_disease` | disease_id | `IRSdiseasecatalog.csv` | 35 rows, has `Phenotype_KOR` + `Phenotype_ENG` → Planning Team slices in Korean for free. |
| `dim_action` | action_no | `iccoli.tb_action_info` | — |
| `dim_deployment_site` | site | — | **Build now even with one row.** The portability matrix is a claim about four sites; if the model cannot express "which site," the matrix is a slide, not a testable claim. |

### 2.3 BI viewer

| # | Decision | Rationale |
|---|---|---|
| D-11 | **Apache Superset (Apache 2.0)** as the viewer | Non-developers author charts and dashboards from a GUI; run synchronously it is a two-container runtime (server + app DB); and everything that matters — the warehouse connection, datasets, the PI dashboard — is scriptable over the REST API, so BI content is reproducible from git rather than living only in an admin's clicks. Apache 2.0 end to end. |
| D-12 | **No custom frontend for KPIs** | Original premise; unchanged. |
| D-13 | **Application database is PostgreSQL, never the embedded default** | An embedded metadata file is the most common way a BI instance becomes unrecoverable. |

> **Terminology — two databases, unrelated purposes.** Confusing them is a common early mistake.
>
> 1. **Data warehouse** — the existing OLAP endpoint holding `stg_*`, `dim_*`, `fct_*`, and the metric views. Superset *reads* from it via the `superset_reader` role. Already exists; nothing new is required here.
> 2. **Superset application database** — Superset's own internal storage: dashboards, charts, users, roles, and the encrypted data-source credentials. Superset requires one to run at all, and it defaults to an embedded file if you do not supply one.
>
> D-13 and D-15 concern (2) only. It can be a container, a managed instance, or simply an additional database on the warehouse server — the requirement is that it is PostgreSQL and that it is backed up, not that it lives on any particular platform. It is small and low-traffic; co-locating it on the warehouse server has no meaningful performance cost at this scale.
| D-14 | **Pin the image tag** (`apache/superset:X.Y.Z` in the deploy Dockerfile), never `:latest` | An auto-pulled major version on restart, with no one to fix the migration, is a dead instance. |
| D-15 | **Backup = scheduled `pg_dump` of the Superset app DB to blob storage. Restore must be tested before departure.** | The app-DB dump is the whole state; the dashboard build script in git regenerates the PI dashboard, but users, roles and any content built in the UI live only in the app DB. An untested backup is not a backup. |
| D-16 | **Dedicated read-only PostgreSQL role scoped to the marts schema only** | The DW holds PII and genomic data. Superset users must never reach `sibc.user_dtc_log` raw. |
| D-17 | **No SQL authoring for the Planning Team.** A dashboards-only role; SQL Lab is for analysts | This is the mechanism that keeps the KPI/PI separation alive after departure. |
| D-18 | **Required config:** `timezone = 'Asia/Seoul'` set **on the warehouse role**, `SUPERSET_SECRET_KEY` (persisted in Key Vault), app DB on PostgreSQL | **Timezone is a correctness issue, not cosmetics.** Partitions run on KST midnight boundaries and `ymd` is a business date. Superset's time grains compile to `date_trunc()` in the warehouse session, so the session timezone IS the report timezone; a UTC session shifts GUI date-grouping on `timestamptz` columns by nine hours and silently disagrees with `ymd`. Enforcing it at the role means no chart setting can undo it. `SUPERSET_SECRET_KEY` encrypts DW credentials at rest — redeploying with a different key orphans every stored secret. |
| D-19 | **Dashboard content is code only where code is cheap.** The PI dashboard is built by one idempotent script; beyond that, do not over-invest in content reproducibility | The viewer is the cheapest layer — the expensive thinking is in dbt and the views. One script keeps the canonical dashboard in git; ad-hoc exploration by users needs no such ceremony and gets none. |

### 2.4 Deployment

| # | Decision | Rationale |
|---|---|---|
| D-20 | **Ship deploy config, not a forked image.** The only Dockerfile content allowed is the one-line driver install on top of the pinned upstream tag | A genuinely custom image forks off upstream — taking a security patch then requires someone to rebuild and republish. The deploy Dockerfile exists solely because upstream ships without a PostgreSQL driver; bumping is a one-line `FROM` change anyone can make. Dashboards live in the app DB and the build script, not the image, so an image cannot usefully carry content anyway. |
| D-21 | ~~Target: Azure Container Apps~~ — **DEFERRED.** No production hosting decision is made. See Q-13 | The organisation may not remain on Azure. Committing the compose file to a specific platform now buys nothing and costs a rewrite later. |
| D-28 | **Build and validate locally first.** `docker-compose.yml` runs Superset plus a `postgres` container for the application database; the warehouse connection is supplied by env var and points at whatever endpoint is in use | Everything that matters — the star schema, dbt models, grain tests, metric views, permission model, dashboards — is hosting-independent. Validating locally removes the cloud-networking dependency (Q-02) from the critical path entirely. The compose file keeps the same shape in production; only the app-DB values change if it later moves to a managed instance. |
| D-29 | **Facts backing behavioural analysis are DENSE.** `fct_user_day` carries every user-day from the earlier of enrolment and first observed activity to the observation frontier, including days with no activity — 5,747 → 74,410 rows (2026-08-07) | A behavioural rate needs the zero days, because the zero days ARE the denominator. Aggregating over an only-active spine divides by the wrong number and biases every rate upward. Demonstrated, not theorised: `DASHBOARD_METRIC_FEEDBACK.md` §5.2 records a published "dietary logging is 미흡" verdict that was a pure denominator artifact — per-recorder intensity had *risen* 6.2 → 21.1 days/month. **Corollary (D-29a):** the spine is bounded, so rows outside its bounds vanish silently — every grain and `not_null` test still passes. `dbt/tests/assert_user_day_spine_loses_no_activity.sql` asserts fact totals equal staging totals per channel. It caught 381 dropped meal records and 23 lost recorders on the first attempt. Do not delete it when editing the spine. |
| D-30 | **The observation frontier, never `current_date`, bounds the panel's upper edge** | Extending to today manufactures zero-activity days for dates the ELT has not loaded yet. A flat line of false zeros at the right edge of every chart reads as a product collapse, and is the kind of artifact that gets escalated before it gets diagnosed. Known limitation, deliberately not modelled: per-channel lag — if one source is stale its recent days read as zeros while others show real activity. Check `dbt source freshness` before reading the last few days of any channel. |

**Deploy layout:**

```
deploy/superset/
├── docker-compose.yml               # pinned image + postgres (app DB) + one-shot init
├── Dockerfile                       # upstream tag + psycopg2 only (D-20)
├── superset_config.py               # app config; mounted read-only
├── .env.example                     # every var documented inline
├── sql/
│   ├── 01_superset_reader_role.sql  # superset_reader, marts only, KST at the role
│   └── 02_superset_grants.sql       # grants + prove-don't-assume verification
├── bootstrap/init_superset.sh       # migrate, admin user, warehouse connection
├── scripts/
│   ├── register_marts_datasets.sh   # marts relations → datasets (idempotent)
│   └── build_pi_dashboard.py        # the PI dashboard, as code
└── METRICS.ko.md                    # 메트릭 추가하는 법
```

The base compose file is the local-development artifact and stays platform-neutral. Production hosting, if and when it is decided, arrives as an override file — not as a rewrite.

### 2.5 PII & data minimisation

The warehouse holds identity, clinical, and genomic data on a 403-user cohort. At that population size, quasi-identifiers combine into identifiers quickly, so minimisation happens at the **T boundary** — data that never enters `stg_*` cannot leak downstream through a view, a dashboard, or an export.

| # | Decision | Rationale |
|---|---|---|
| D-22 | **Username is dropped during transform.** It does not appear in `stg_*`, `dim_*`, or `fct_*` | Direct identifier with no analytical use. Dropping at staging means no downstream model can reintroduce it by accident. |
| D-23 | **Date of birth is reduced to `birth_year` (integer) at staging.** Full DOB is never materialised in the warehouse | DOB is a strong quasi-identifier; birth year alone supports every age-stratified analysis in the driver tree. |
| D-24 | **Age at activity is imputed from a fixed mid-year anchor: `july 1` of the birth year.** SQL: `age_at_activity = (ymd - make_date(birth_year, 7, 1)) / 365.25` | Convention, not preference — July 1 is the standard demographic mid-year anchor (UN population estimates use it), so the choice is defensible and reproducible. Pick one and never vary it; alternating between June 30 and July 1 across models produces off-by-one age bands that are impossible to debug later. **Known measurement limit: ±6 months maximum error.** Acceptable for 5- and 10-year bands; must be disclosed if any bridge or gate query stratifies on narrower age intervals. |
| D-25 | **`age_at_activity` is materialised as a column in the facts, not stored in `dim_user`** | `dim_user` is SCD Type 1 (D-08) and age is time-varying — a static age column would silently rot. Materialising in the fact also means Superset GUI users get age without needing to compute it, which they cannot do. |
| D-26 | **JSONB flattening in the `irs` and `sibc` schemas uses an explicit allow-list of extracted keys, not a deny-list.** Names, ages, and any other identity fields are excluded by omission | This is the load-bearing form of the decision. The backend schema docs state `모델/룰 변경으로 키 확장 가능` — the JSONB payload is a moving contract. A deny-list means a newly added `patient_name` key flows straight through to staging on the next model release, silently. An allow-list fails safe: unknown keys are ignored by default. |
| D-27 | **Pair the allow-list with a schema-drift test** that flags top-level JSONB keys not present in the allow-list | Allow-listing alone makes drift invisible; the pairing gives fail-safe behaviour *and* visibility. Complements D-05. |

**Not yet a decision — see Q-11.** The working assumption that schemas other than `irs` and `sibc` already carry an adequate anonymisation policy has not been verified. `iccoli` is the auth/identity layer and is the schema most likely to hold phone numbers, email addresses, device identifiers, and CI/DI values. Assumption, not finding.

### 2.6 Sequencing (remaining ~2 weeks)

| Days | Work |
|---|---|
| 1–2 | dbt Core init, profiles against Azure PG, staging models flattening JSONB → `stg_*`, tests on extracted-field nullity |
| 3–5 | `dim_*` + `fct_user_day` + `fct_user_disease_day`, grain tests. **Load-bearing** — if only this ships, the handover still works |
| 6–7 | Remaining facts; `dbt build` wired into Airflow; `dbt docs` published somewhere findable |
| 8–10 | Superset deployed on the marts; the PI dashboard; permissions locked to marts-only; backup restore-tested |
| 11–14 | Metric views for T1/T2 PIs; Korean runbook + metrics doc |

**Cut order if time runs out:** metric views first (rebuildable from the star), then dashboards, then remaining facts. **Never cut the grain tests** — they are what makes the rest survivable.

---

## 3. NEEDS DECISION

| # | Question | Why it blocks | Suggested resolution path |
|---|---|---|---|
| Q-01 | **Does `sibc.user_intg_log` produce more than one meaningful row per user per `ymd` after dedupe?** Is `created_at` an append with last-row-wins, or are there genuine intra-day revisions? | Determines whether `fct_user_day` has a clean grain or is a slowly-changing fact. Changes the model and the test. | Single query: `SELECT user_id, ymd, count(*) FROM sibc.user_intg_log GROUP BY 1,2 HAVING count(*) > 1`. Same for `user_irs_log`. |
| Q-02 | **Is the warehouse PostgreSQL behind a private endpoint, or does it allow access from outside its network?** *(Conditional on Q-13 — not on the critical path while development is local)* | Determines whether a hosted Superset needs VNet integration or a gateway. Can eat two days if IT is slow. | Ask IT once a production target is chosen. Does not block local work. |
| Q-03 | **Does anyone at Invites Ecosystem already run a BI tool?** | Institutional gravity beats tool quality on a two-week clock. An existing instance with an existing owner is better than a new orphan. | Ask the Planning Team / IT. |
| Q-04 | **Who owns the Superset instance and the Azure resources after departure — named, in writing?** | The most likely failure mode is not technical. An orphan container with no line in anyone's job description gets deleted or ignored. | Raise with the counterpart before the last day. Not optional. |
| Q-05 | **Incremental strategy per fact model** | Partitioned append-only logs suit `incremental` with a `created_at` watermark, but the late-arriving-data window needs a number. | Decide per model during Days 3–5. |
| Q-06 | **`dim_user` attribute list** — which attributes are actually needed to slice the driver tree? | Over-wide dims add maintenance; missing attributes block analysis. | Derive from the driver tree Layer 2 slice requirements. |
| Q-07 | **Where do `dbt docs` get hosted?** | The junior's primary onboarding artifact. If it is not findable it does not exist. | Azure Blob static site, or commit generated HTML to the repo. |
| Q-08 | **Do Jeju / Mode C metrics get placeholder models, or are they omitted until the deployments exist?** | Placeholders that always return NULL erode trust in the dashboard; omission loses the roadmap signal. | Recommend: omit from marts, document in the Bridge Register. |
| Q-09 | **Does the `grmc` schema enter the same warehouse and the same Superset instance?** | Different clinical/regulatory posture and a different audience. Affects the read-only role and permission model. | Decide before writing the read-only role SQL. |
| Q-10 | **Which identifier is elected canonical — `iccoli.user_no` or `invites_loop.user_id`?** Mapping table is `iccoli.public.tb_ext_user_mapper` | Blocks `dim_user` and every fact that joins across the two systems. See resolution notes below — this is the most consequential open item after Q-01. | Run the cardinality checks below before choosing. |
| Q-11 | **PII inventory across all source schemas — is the "already anonymised" assumption for `iccoli`, `discovery`, and `ichms` actually true?** | D-22–D-27 harden `irs` and `sibc`. If `iccoli` carries phone/email/CI-DI and those fields flow into `stg_*` unexamined, the minimisation policy has a hole in exactly the schema most likely to contain direct identifiers. | Enumerate columns via `information_schema.columns` across all source schemas; classify each as identifier / quasi-identifier / analytical; document the result. Half a day, and it is the difference between a policy and a belief. |
| Q-12 | **Is raw `age_at_activity` exposed to Superset, or only banded age?** | At n=403, birth year + deployment site + sex is close to identifying. Raw age in a GUI-filterable column makes small-cell exposure trivially reachable. | Recommend: expose `age_band_5y` in the Superset-visible layer by default; keep raw `age_at_activity` in the fact for view-layer computation only. Decide before permissions are set. |
| Q-13 | **Production hosting target for Superset, and where the application database lives.** Deliberately deferred | Not on the critical path. The organisation may leave Azure, and no part of the modelling work depends on the answer. | Revisit after local validation. Decision criteria below. |

### Q-10 resolution notes — canonical user key

**This is a key-election problem, not a key-minting problem.** Do not hash `user_no` and `user_id` together into a synthetic key; that creates a third identifier that maps to neither source system and makes every debugging session worse. Elect one of the two existing keys and translate the other.

**Run these first — the answer may make the choice for you:**

```sql
-- 1. Is the mapper 1:1, or does it fan out?
SELECT
  (SELECT count(*) FROM iccoli.public.tb_ext_user_mapper)              AS rows,
  (SELECT count(DISTINCT user_no) FROM iccoli.public.tb_ext_user_mapper) AS distinct_user_no,
  (SELECT count(DISTINCT user_id) FROM iccoli.public.tb_ext_user_mapper) AS distinct_user_id;

-- 2. Orphans in each direction
--    (users present in one system with no counterpart)
```

If either side fans out — re-enrolment, device change, account merge — the mapper is not a simple lookup and joining through it will multiply fact rows. That case needs an explicit resolution rule (latest mapping wins, or a genuine bridge table), decided before any model is written.

**Provisional recommendation, pending the cardinality result: elect `invites_loop.user_id`.**

1. **Join surface.** The facts carrying the analytical payload — IRS scoring, SiBC coaching, device measurement — already sit in `invites_loop` and already carry `user_id`. Electing it means only `fct_app_action` needs translation, rather than translating four fact models to accommodate one.
2. **Deployment portability.** `iccoli` is the app identity layer and is plausibly per-deployment. A UUID namespace extends cleanly to Jeju, GRMC, and Shenzhen; a per-instance serial does not, and D-10's `dim_deployment_site` decision assumes multi-site is real.
3. **Leakage surface.** A sequential integer leaks enrolment ordering and cohort size. A UUID does not.

**Verify before committing:** if `tb_ext_user_mapper` shows `user_no` as the master and `user_id` as derived per-service, argument 2 inverts and `user_no` becomes the better anchor. Check the directionality rather than assuming it.

**Where the translation happens:** in **staging**, once per `stg_iccoli_*` model. No mart model should ever see `user_no`. This keeps the mapper as a single point of contact instead of a join scattered across fifteen models.

**Join hygiene:** left-joining to the mapper and then filtering in an outer `WHERE` silently converts it to an inner join and drops unmapped users without any signal. Filter inside the CTE, and add a `not_null` test on the resulting key plus an explicit orphan count so unmapped users are a reported number rather than a silent absence.

### Q-13 resolution notes — production hosting (deferred)

Nothing below is decided. Recorded so the eventual decision is made against criteria rather than defaults.

**The only requirement that survives any hosting choice:** the Superset application database is PostgreSQL (D-13) and is backed up with a *tested* restore (D-15). Everything else is negotiable.

**Options for the application database, in rough order of operational burden:**

| Option | Who owns the backup | Notes |
|---|---|---|
| Postgres container beside Superset | You | Correct for local development. In production it means someone must own the backup script and its cron. |
| Additional database on the existing warehouse server (`CREATE DATABASE superset_app`) | The platform | No new resource, no new cost, no procurement. Inherits whatever backup policy the warehouse already has. Usually the pragmatic answer. |
| Separate managed instance | The platform | Cleanest isolation, but a new resource to justify and pay for. Hard to argue for at this scale. |

**Options for the Superset runtime:**

| Option | Trade-off |
|---|---|
| Managed container service (Azure Container Apps, Cloud Run, ECS/Fargate) | No OS to patch — the main argument. Needs `minReplicas: 1`, since a cold start makes scale-to-zero look like an outage. |
| VM with docker-compose | Simplest to reason about, and platform-portable. Cost: an OS that someone must patch, and nobody will. |
| Existing internal container platform, if one exists | Best organisational survival — it already has an owner and a patching process. Check before evaluating anything else. |

**Decision criteria, when the time comes,** in priority order: (1) which option has a named owner already (Q-04); (2) whether the warehouse endpoint is reachable from it (Q-02); (3) who owns OS patching; (4) portability if the organisation leaves its current cloud.

---

## 4. REJECTED

### 4.1 BI viewers

| Option | Reason for rejection |
|---|---|
| **Custom-built frontend** | No reason to build UI for numerous KPIs. Original premise. |
| **Microsoft Power BI** | Pro is **not** included in M365 Business Basic/Standard/Premium — only E5. Pro is ~$14/user/month (raised from $10 in April 2025) and is required for **viewers**, not just authors, unless reports sit on Fabric capacity. PPU is $24/user/month. Licensing cost for the Planning Team is not approvable in the available time. *(Secondary concerns, now moot: `.pbix` is a binary and not diffable; DAX would become a second, unreviewed metric layer; a data gateway VM would be needed behind a private endpoint.)* |
| **Metabase OSS** | The closest contender: GUI authoring with a one-moving-part runtime, automatic schema sync, and FK-metadata-driven implicit joins. Rejected on reproducibility and licence: on OSS the warehouse connection and all content are UI-only (config-as-code serialization is Pro/Enterprise), so a rebuilt instance starts empty with no path from git; the licence is AGPL against Superset's Apache 2.0; the report timezone is an app setting rather than something enforceable at the database; and the current release line EOLs roughly every two months, putting an upgrade treadmill on whoever inherits the instance (Q-04). The implicit-join convenience is real but replaceable by pre-joined wide datasets (`HOWTO.md` §3), which also remove the fan-out risk the join UI invites. |
| **Redash** | Project is in maintenance mode (community-led, ~7 volunteer maintainers, roughly one release per year since 2022; forum read-only). Independently disqualifying: every dashboard requires hand-written SQL, so non-developers cannot author. |
| **Lightdash** | Best governance fit: metric definitions become dbt YAML in git, which line 39 of this log wants and Lightdash *enforces* where Superset merely permits. A commercial tier with SOC 2 / HIPAA / BAA would also give a compliance escalation path (Q-04). Rejected: every metric change becomes a git PR, which no Planning Team member will open — the `v_pi_*` views already give the git-reviewed layer without gating the GUI on it. Korean locale coverage also unverified. |
| **Power BI + Superset hybrid** | Two tools means two decay paths and two places for the Planning Team to find contradictory numbers. |

### 4.2 Transformation

| Option | Reason for rejection |
|---|---|
| **dbt Cloud / Starter / Enterprise** | Starter is $100/user/month; Canvas and Insights sit behind custom-priced Enterprise. Nothing in the design requires them. |
| **dbt Studio (hosted IDE)** | Substituted by VS Code + the free **dbt Power User** extension (model preview, lineage, go-to-definition). |
| **dbt Canvas (visual model builder)** | Rejected on principle even if free. The point of putting transforms in dbt is that changes are diffable text under review; a GUI model editor reintroduces exactly the drift being prevented. |
| **dbt Fusion** | ELv2 license. Stay on Core (Apache 2.0). |
| **Raw Airflow SQL for T** | Fails silently. A task runs, the grain doubles because someone added a join, and the dashboard shows plausible wrong numbers. No test framework, no lineage, hand-maintained task dependencies. |
| **SQLMesh** | Technically better (column-level lineage, virtual environments, no Jinja soup). Rejected on handover grounds: far smaller community, and Tobiko Data was acquired by Fivetran too, so it is not even a vendor hedge. Handover quality is a function of how many answers exist for the error message. |
| **astronomer-cosmos** | Deferred, not permanently rejected. One more dependency for the junior to debug; unnecessary at ~15 models. Revisit if the model count grows materially. |

### 4.3 Superset-specific

| Option | Reason for rejection |
|---|---|
| **Redis + Celery (async queries, alerts/reports, thumbnails)** | Not required to run Superset — they buy async execution and scheduled reports. At this scale the synchronous two-container runtime is enough, and every extra service is a thing that breaks with nobody qualified to fix it. Revisit only if alerts/reports become a real requirement. |
| **A genuinely custom Docker image (beyond the one-line driver install)** | Forks off the upstream tag, making security patches a rebuild-and-republish task that will not happen. Dashboards live in the app DB and the build script, so the image cannot usefully carry content anyway (D-20). |
| **Dashboard export/import ZIPs in git as the content source of truth** | The export format is UUID-laden YAML bundles — technically in git, practically unreviewable. The REST-API build script is diffable, idempotent, and carries the layout and interpretation notes in readable code. |
| **Preset (hosted Superset)** | A new vendor and a new resource to justify while no production hosting is decided at all (Q-13). Local-first (D-28) stays. |
| **VM deployment** | Not rejected outright — reopened under Q-13. The objection stands (an OS somebody must patch, and nobody will), but it is a trade-off against portability rather than a disqualification. |

### 4.4 PII handling

| Option | Reason for rejection |
|---|---|
| **Deny-list for JSONB key extraction** | The JSONB payload is a moving contract by design (`모델/룰 변경으로 키 확장 가능`). A deny-list passes any newly added identity key straight through to staging on the next model release, with no signal. Allow-list fails safe. |
| **Storing full date of birth in the warehouse** | Strong quasi-identifier with no analytical benefit over birth year at this cohort size. |
| **Masking / hashing usernames instead of dropping them** | A hashed username is still a stable per-person identifier and still supports linkage. It carries no analytical value, so retention in any form is unjustified. |
| **Storing a static `age` column in `dim_user`** | `dim_user` is SCD Type 1. A static age silently rots and produces wrong stratification within a year. |
| **Minting a synthetic hash key from `user_no` + `user_id`** | Creates a third identifier mapping to neither source system, making every trace-back harder for exactly the person least equipped to do it. Elect an existing key instead (Q-10). |

### 4.5 Scope

| Option | Reason for rejection |
|---|---|
| **Building dashboards for the headline chairman-level KPIs** | Established previously: they have zero source tables in the current estate. A dashboard full of NULLs is worse than no dashboard. Build the T1/T2 PI layer instead. |
| **Building 50 dashboards before departure** | Three good ones that demonstrate the pattern are more transferable than fifty that nobody understands. |

---

## 5. Handover artifacts (deliverable checklist)

- [ ] `invites_loop_bi` dbt project (models, tests, `dbt docs`) in git
- [ ] `deploy/superset/` stack (compose, env template, role SQL, dataset + dashboard scripts)
- [ ] Superset running, marts-only read-only role, Planning-Team role configured
- [ ] Verified backup restore (performed, not merely scripted)
- [ ] `SUPERSET_SECRET_KEY` stored in Key Vault and referenced in the runbook
- [ ] `RUNBOOK.ko.md` — 이게 안 될 때 (container restart, backup restore, resource ownership)
- [ ] `METRICS.ko.md` — 메트릭 추가하는 법 (edit view SQL → PR → build → register dataset in Superset)
- [ ] Named owner for Superset instance and Azure resources, in writing (Q-04)
- [ ] PII inventory across all source schemas, classified identifier / quasi-identifier / analytical (Q-11)
- [ ] JSONB extraction allow-list committed as a versioned file, with the schema-drift test wired into `dbt build` (D-26, D-27)

---

## 6. Notes for Claude Code

- Language convention: **English** for technical specs and code; **Korean** for stakeholder-facing and internal organizational materials (runbook, metrics guide, meeting materials).
- Decisions in section 2 carry rationale for a reason — do not silently reverse one. If a decision looks wrong, surface the conflict with its stated rationale rather than working around it.
- The KPI / PI / Bridge separation is load-bearing. Conflating the layers is a known failure mode. Metric views must keep their tier prefix.
- Items in section 3 are genuinely open. Do not resolve them by assumption. **Q-01 and Q-10 both change the data model and both block Day 1–2 work** — run their diagnostic queries before writing any staging model.
- PII minimisation (§2.5) happens at the T boundary by design. If a downstream request needs a field that was dropped at staging, that is a policy conversation, not a model edit — do not quietly reintroduce it.
- **Development is local-first (D-28) and no production hosting is decided (Q-13).** Do not add cloud-provider-specific resources, IaC, or CLI dependencies to the deploy repo. The base `docker-compose.yml` must stay runnable on a laptop with nothing but Docker installed.
- This document is scoped to the BI stack. Adjacent open items in the broader BI programme (device allocation randomness, NHIS refresh path for MRS, `watermark_manager.py` scope, Bayesian Network pilot) live in their own artifacts and are out of scope here.
