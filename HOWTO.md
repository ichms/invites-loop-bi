# HOWTO

Three operational tasks that come up repeatedly:

1. [Restricting what an MCP / AI client can do](#1-restricting-what-an-mcp--ai-client-can-do)
2. [Adding a dim or fact table to the marts](#2-adding-a-dim-or-fact-table-to-the-marts)
3. [Joining tables in Superset (filtering across tables)](#3-joining-tables-in-superset)

Everything here was verified against the running stack on 2026-08-11. Where
something is stated but *not* verified, it says so.

---

## 1. Restricting what an MCP / AI client can do

An AI client (Claude Code, Claude Desktop) reaches this data two ways: a
direct PostgreSQL connection to the warehouse, or Superset's REST API. The
enforcement story is different for each, and only one layer actually
protects the data.

### The layer that enforces: the database role

The PII boundary is `superset_reader` (deploy/superset/sql/): read-only at
the transaction level, `marts`-only by grant, proved by the verification
block in `02_superset_grants.sql`. A session as that role **cannot** reach
`stg_sibc.chat_msgs` or any landing schema — `permission denied for schema`
— regardless of what the client asks for.

**The practical conclusion:** give an AI client its own DB credentials with
exactly `superset_reader`'s grants (or `superset_reader` itself, read-only),
and never `analytics_user`, which owns every schema. An MCP Postgres
connector configured with a marts-only role is safe by construction; the
same connector with the dbt credentials can read raw identity and clinical
tables. The role *is* the permission system — everything else is UX.

### The layer that does not: application-side controls

Superset's REST API is authenticated by its own users and roles. Two things
to internalise:

- An **Admin** API session can create and modify charts, dashboards and
  database connections — including registering a *new* warehouse connection
  under different credentials. Handing an agent an admin login is equivalent
  to handing it whatever credentials that admin can type in. Scope agents to
  a non-admin account.
- SQL Lab enforces the role timeouts and blocks a list of introspection and
  abuse functions (`pg_sleep`, `version`, `current_setting`, …) — verified
  2026-08-11. Useful hygiene, but it is defence in depth on top of the DB
  role, not a substitute for it.

> **Not yet configured:** a Planning-Team Superset role (dashboards only, no
> SQL Lab). Superset's Gamma role minus `can sql_json` is the intended
> shape; it has not been set up or tested yet. Until it is, every Superset
> login can open SQL Lab — the DB role still caps what that can read.

---

## 2. Adding a dim or fact table to the marts

Five steps. Skipping step 5 is the usual reason a new table "doesn't show up".

### Step 1 — write the model

Create `dbt/models/marts/<name>.sql`. Facts get a grain declaration in a header
comment — that comment is the contract the test enforces (D-04).

```sql
-- GRAIN: one row per (user_id, ymd_date). Enforced in marts.yml.
--
-- Say what the model is for and any caveat a reader would otherwise trip on.

with base as (

    select ... from {{ ref('stg_sibc__user_intg_log') }}

),

users as ( select user_id from {{ ref('dim_user') }} )

select ...
from base
inner join users using (user_id)   -- cohort guard: no non-cohort rows leak in
```

Conventions in this project:
- `ref()` staging models — never a raw `stg_<system>` source from a mart.
- Facts inner-join `dim_user` so only cohort users appear.
- Dims are one row per entity, SCD1 (D-08): no history, no static age.
- Tab indentation.

### Step 2 — declare tests

In `dbt/models/marts/marts.yml`:

```yaml
  - name: fct_your_new_fact
    description: "GRAIN: user × ymd. What it measures."
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns: [user_id, ymd_date]
    columns:
      - name: user_id
        data_tests:
          - not_null
          - relationships:
              arguments: {to: ref('dim_user'), field: user_id}
      - name: ymd_date
        data_tests:
          - not_null
          - relationships:
              arguments: {to: ref('dim_date'), field: date_day}
```

The grain test is mandatory on every fact. The `relationships` tests are what
catch a key that stops joining — add one per FK. They are also the committed
record of which joins are legal (see §3).

### Step 3 — build

```bash
source setup_env.sh
uv run dbt build --project-dir dbt --select fct_your_new_fact
uv run dbt build --project-dir dbt          # full run before committing
```

### Step 4 — grants (usually automatic)

`ALTER DEFAULT PRIVILEGES` already covers new objects in `marts`, so
`superset_reader` can read them without action. Verify if a table appears
empty in Superset:

```bash
PGPASSWORD='...' psql "host=... dbname=invites_dw user=superset_reader sslmode=require" \
  -c "select count(*) from marts.fct_your_new_fact;"
```

If that fails, re-run `deploy/superset/sql/02_superset_grants.sql` as
`analytics_user`.

### Step 5 — register the dataset in Superset

Superset does not schema-sync. A new relation becomes chartable only when a
dataset exists for it:

```bash
cd deploy/superset
./scripts/register_marts_datasets.sh    # idempotent; skips existing datasets
```

**Without this the new table cannot be used in a chart at all.** This is the
step people miss. If the model belongs on the PI dashboard, also add it to
`CHARTS` / `LAYOUT` in `scripts/build_pi_dashboard.py` and re-run it — the
dashboard is code, and UI-only edits are overwritten on the next run.

---

## 3. Joining tables in Superset

### The ground rule: a chart reads ONE dataset

The star schema uses natural keys, not surrogate keys (D-07), and dbt does
not create foreign-key constraints in PostgreSQL. Superset's Explore view
does not join for you either way: **every chart is built on exactly one
dataset**. Cross-table questions are answered by making a dataset that
already contains the join — in dbt (preferred) or as a virtual dataset.

The join graph itself lives in git as the 14 `relationships` tests in
`dbt/models/marts/marts.yml`. That file is the statement of which joins are
legal and on which keys:

| From | Column | To |
|---|---|---|
| `fct_user_day` | `user_id` | `dim_user.user_id` |
| `fct_user_day` | `ymd_date` | `dim_date.date_day` |
| `fct_user_disease_day` | `user_id` | `dim_user.user_id` |
| `fct_user_disease_day` | `ymd_date` | `dim_date.date_day` |
| `fct_user_disease_day` | `disease_id` | `dim_disease.disease_id` |
| `fct_coaching_event` | `user_id` | `dim_user.user_id` |
| `fct_coaching_event` | `ymd_date` | `dim_date.date_day` |
| `fct_measurement` | `user_id` | `dim_user.user_id` |
| `fct_measurement` | `measured_date` | `dim_date.date_day` |
| `fct_measurement` | `device_type_id` | `dim_device_type.device_type_code` |
| `fct_app_action` | `user_id` | `dim_user.user_id` |
| `fct_app_action` | `action_no` | `dim_action.action_no` |
| `fct_app_action` | `action_date` | `dim_date.date_day` |
| `dim_user` | `site_id` | `dim_deployment_site.site_id` |

### Option A — pre-join in dbt (recommended for the Planning Team)

When a question needs a fact filtered by dimension attributes, ship a wide
model — the fact with those attributes already attached — and register it as
a dataset. The Planning Team then filters plain columns, no SQL, no join UI,
and no chance of two people joining differently.

```sql
-- marts/fct_user_disease_day_wide.sql
select
    f.*,
    u.sex,
    u.birth_year,
    d.phenotype_kor,
    d.phenotype_eng
from {{ ref('fct_user_disease_day') }} as f
left join {{ ref('dim_user') }}    as u using (user_id)
left join {{ ref('dim_disease') }} as d using (disease_id)
```

Then steps 2–5 of §2 apply as for any model (grain test, build, grants are
automatic, register the dataset).

Trade-off: it duplicates dimension attributes and grows with the fact
(`fct_user_disease_day` is ~181k rows and projected to millions per year), so
do it for genuinely repeated joins, not speculatively. The star stays the
source of truth; the wide model is a convenience layer over it.

Use **left join** for fact→dim lookups: it keeps fact rows whose dimension
row is missing rather than silently dropping them. An inner join hides those
rows — occasionally what you want, but know that you are deleting evidence.

### Option B — virtual dataset (analyst-authored, no dbt round-trip)

A SQL Lab query can be saved as a **virtual dataset** (Save → Save dataset)
and charted like any physical one. Right for an exploratory join an analyst
wants to visualise today.

The cost: the SQL lives in Superset's app DB, not in git, and gets no dbt
tests. The moment a virtual dataset is used by more than one chart or one
person, promote it to a dbt model (Option A) — same rule as metrics: shared
definitions live in git, reviewed.

### Option C — ad hoc SQL in SQL Lab

For a one-off answer that will not become a chart, just write the join in
SQL Lab. The role timeouts (120 s) and the function denylist apply; results
are capped by `SQL_MAX_ROW`.

### Which option to use

| Situation | Use |
|---|---|
| Ongoing self-service for the Planning Team | **A** — pre-join in dbt, register the dataset |
| Reusable exploration by an analyst | **B** — virtual dataset, promote to dbt when shared |
| A one-off answer, no chart | **C** — SQL Lab |
| A number that will be quoted in meetings | A metric view (`v_pi_*`) — see `deploy/superset/METRICS.ko.md` |

### Interpretation traps when joining

- **Fan-out.** Joining `dim_user` (404 rows) to `fct_user_disease_day` (181k
  rows) is safe — one dim row per fact row. Joining two *facts* on `user_id`
  alone multiplies rows and inflates every count. Join facts only on their full
  shared grain (e.g. `user_id` **and** `ymd_date`), or aggregate one side first.
- **Percentile scores are not additive.** IRS/IRS+/LRS/MRS/PRS are 1–100 ranks.
  Averaging across diseases is defensible; summing is not.
- **The 9 non-catalog diseases.** `fct_user_disease_day` carries 44 disease ids;
  only 35 are user-facing. Filter `is_in_catalog = true`, or join `dim_disease`
  (which contains only the 35) with an inner join.
- **Check coverage before reading a trend.** See
  `v_pi_scoring_coverage_monthly` — a month where fewer users were scored can
  make risk look like it improved.
- **Date grain.** `dim_date.date_day` is a `date`. A *timestamp* column (e.g.
  `fct_measurement.measured_at`) does not join to it; use the `_date` column
  that exists for exactly this purpose.
