# HOWTO

Three operational tasks that come up repeatedly:

1. [Restricting what an MCP / AI client can do](#1-restricting-what-an-mcp--ai-client-can-do)
2. [Adding a dim or fact table to the marts](#2-adding-a-dim-or-fact-table-to-the-marts)
3. [Joining tables in Metabase (filtering across tables)](#3-joining-tables-in-metabase)

Everything here was verified against the running stack on 2026-08-06. Where
something is stated but *not* verified, it says so.

---

## 1. Restricting what an MCP / AI client can do

Metabase runs a built-in MCP server at `/api/metabase-mcp`, so an AI client
(Claude Code, Claude Desktop) can query the warehouse directly. It needs no AI
provider key of its own — the client brings its own model.

### What the server actually exposes

15 tools, in three groups:

| Group | Tools |
|---|---|
| Read / query | `search`, `read_resource`, `query`, `construct_query`, `execute_query`, `execute_question` |
| SQL | `construct_native_query`, `execute_sql` |
| Write | `create_question`, `create_dashboard`, `create_metric`, `create_collection`, `update_question`, `update_dashboard`, `update_metric` |

### The three layers, and which one actually protects what

Tested 2026-08-06 with two group-scoped API keys (Administrators vs Planning
Team). The results are worth internalising before changing anything:

| Layer | What it does | Verified behaviour |
|---|---|---|
| **1. Tool visibility** | Which tools the client can see | **Does not restrict.** A Planning Team key sees all 15 tools, `execute_sql` included. Do not treat the tool list as a permission boundary. |
| **2. Metabase group permission** | Whether the call is allowed to run | **Enforces.** Planning Team → `execute_sql` returns *"You do not have permission to run native queries against this database."* D-17 survives MCP. |
| **3. `bi_reader` DB role** | What data is reachable at all | **Enforces, even for admins.** An admin key ran `select … from stg_sibc.chat_msgs` and got `ERROR: permission denied for schema stg_sibc`. |

**The practical conclusion:** the controls that matter are the Metabase group
permission and the `bi_reader` role — the same two that protect the browser.
MCP does not open a side door around them. This is defence in depth working as
designed (D-16 + D-17), demonstrated through a second access path.

**One real gap:** write tools are *not* blocked for Planning Team. A Planning
Team key successfully created a collection in testing. That is the same
authority they have in the browser, but it is now reachable by an agent acting
on a loosely-worded instruction. Decide whether that is acceptable.

### Lever A — instance-wide settings (simplest, coarsest)

These exist and are settable via Admin → Settings, or the API:

| Setting | Effect |
|---|---|
| `mcp-enabled?` | Master switch for the MCP server |
| `agent-api-enabled?` | The Agent API that backs MCP |
| `mcp-execute-sql-enabled` | **Kills the `execute_sql` tool instance-wide**, for everyone including admins |
| `mcp-apps-cors-enabled-clients` | Which clients may connect (currently `["claude", "chatgpt"]`) |

Read current values:

```bash
curl -s -H "X-Metabase-Session: $SESSION" http://localhost:3000/api/setting \
  | python3 -c "import json,sys; [print(s['key'],'=',s.get('value')) for s in json.load(sys.stdin) if 'mcp' in s['key'] or 'agent' in s['key']]"
```

Set one:

```bash
curl -s -X PUT http://localhost:3000/api/setting/mcp-execute-sql-enabled \
  -H "X-Metabase-Session: $SESSION" -H 'Content-Type: application/json' \
  -d '{"value": false}'
```

**`mcp-execute-sql-enabled: false` is the blunt, reliable option.** It removes
raw-SQL execution over MCP for everyone. Given that group permissions already
block SQL for the Planning Team, this mainly closes the admin path — useful if
you want the MCP surface to be strictly read-and-explore.

### Lever B — OAuth scopes (granular, per-token)

Metabase runs its own OAuth server (embedded; no external IdP). Clients
register dynamically at `/oauth/register` and authorise at `/oauth/authorize`
(PKCE `S256`). The grantable scopes:

```
agent:search              agent:resource:read
agent:query               agent:query:construct     agent:query:execute
agent:sql:construct       agent:sql:execute            ← withhold to block SQL
agent:question:create     agent:question:update        agent:question:execute
agent:dashboard:create    agent:dashboard:update       ← withhold to block writes
agent:metric:create       agent:metric:update
agent:collection:create
agent:viz:mcp-ui:query    agent:viz:mcp-ui:drill-through
mb:full                                                 ← everything; avoid
```

A read-only analyst token wants roughly:

```
agent:search  agent:resource:read  agent:query  agent:query:construct  agent:query:execute
```

…and specifically **not** `agent:sql:*`, not the `create`/`update` scopes, and
never `mb:full`.

> **Not yet verified:** how to *force* a client to receive only a subset. The
> scopes are advertised and the consent step exists, but whether Metabase lets
> an admin cap the grantable set per client (versus the client asking politely
> for less) was not tested. Until that is confirmed, treat Lever A + group
> permissions as the enforcement, and scopes as defence in depth.

### Checking discovery / auth from the shell

```bash
curl -s http://localhost:3000/.well-known/oauth-protected-resource/api/metabase-mcp | python3 -m json.tool
curl -s http://localhost:3000/.well-known/oauth-authorization-server | python3 -m json.tool
```

### Connecting Claude Code

```bash
claude mcp add --transport http metabase http://localhost:3000/api/metabase-mcp
# then run /mcp inside Claude Code to complete the OAuth consent
```

The token is scoped to whichever Metabase account the **browser** is logged in
as. Check with <http://localhost:3000/api/user/current> before authorising. MCP
tools load at session start, so start a new session after connecting.

Claude **Desktop** additionally requires a publicly reachable HTTPS endpoint —
it does not permit local connections. That is a hosting decision (Q-13), and it
means cohort data would leave the machine; treat it as a policy conversation,
not a config change.

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
catch a key that stops joining — add one per FK.

### Step 3 — build

```bash
source setup_env.sh
uv run dbt build --project-dir dbt --select fct_your_new_fact
uv run dbt build --project-dir dbt          # full run before committing
```

### Step 4 — grants (usually automatic)

`ALTER DEFAULT PRIVILEGES` already covers new objects in `marts`, so
`bi_reader` can read them without action. Verify if a table appears empty in
Metabase:

```bash
PGPASSWORD='...' psql "host=... dbname=invites_dw user=bi_reader sslmode=require" \
  -c "select count(*) from marts.fct_your_new_fact;"
```

If that fails, re-run `sql/02_grants.sql` from the deploy repo as
`analytics_user`.

### Step 5 — sync Metabase, then set FK metadata

Admin → Databases → *Invites Loop DW (marts)* → **Sync database schema now**.

Then set the foreign keys (section 3) — **without this the new table cannot be
joined in the query builder.** This is the step people miss.

---

## 3. Joining tables in Metabase

### Why joins don't work yet

The star schema uses natural keys, not surrogate keys (D-07), and **dbt does
not create foreign-key constraints in PostgreSQL**. Metabase infers join
relationships from FK constraints during sync — with none present, it sees
eleven unrelated tables.

Measured 2026-08-06: **0 of 21 key columns are marked as foreign keys.** That is
the whole reason cross-table filtering isn't available in the GUI.

There are three ways forward.

### Option A — set FK metadata (recommended; do this once)

This is the intended path and the reason the star schema exists (D-06: Metabase
reads FK metadata into join dropdowns). Once set, a Planning Team member can
filter a fact by a dimension attribute without writing any SQL — e.g. filter
`fct_user_disease_day` by `dim_disease.phenotype_kor` and `dim_user.sex` at the
same time.

**In the UI:** Admin → Table Metadata → pick the database → pick a table →
find the column → set **Field Type** to *Foreign Key* → choose the target field.

The relationships to set:

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

**Via the API** (faster than 14 UI visits). For each pair, find the field ids
and PUT the semantic type:

```bash
# 1. find field ids
curl -s -H "X-Metabase-Session: $SESSION" \
  http://localhost:3000/api/database/2/metadata \
  | python3 -c "
import json,sys
for t in json.load(sys.stdin)['tables']:
    for f in t['fields']:
        print(t['name'], f['name'], f['id'])
"

# 2. mark one column as an FK pointing at a target field id
curl -s -X PUT http://localhost:3000/api/field/<FIELD_ID> \
  -H "X-Metabase-Session: $SESSION" -H 'Content-Type: application/json' \
  -d '{"semantic_type": "type/FK", "fk_target_field_id": <TARGET_FIELD_ID>}'
```

After setting them, re-sync the database so the query builder picks up the
relationships.

**Caveat on the date FKs.** `dim_date.date_day` is a `date` and the fact columns
are `date` — they join cleanly. But a *timestamp* column (e.g.
`fct_measurement.measured_at`) will not join to `dim_date`; use the `_date`
column that exists for exactly this purpose.

### Option B — explicit joins in the notebook editor

Works without FK metadata, and is the right tool for a one-off question.

1. New → Question → pick the starting table (usually the fact).
2. Click **Join data**, pick the second table.
3. Metabase proposes the join columns — with FK metadata set it fills them in;
   without, pick them manually (`user_id` = `user_id`).
4. Add more joins for more tables.
5. Filter on any column from any joined table — this is what "filter multiple
   items across tables" needs.
6. Summarise, then Visualise.

Join type defaults to **left join**. For a fact→dim lookup that is correct: it
keeps fact rows whose dimension row is missing, rather than silently dropping
them. Switching to inner join hides those rows — occasionally what you want,
but know that you are deleting evidence.

### Option C — pre-join in dbt

When the same join appears in question after question, put it in a model rather
than making every author rebuild it. A wide model — the fact with its dimension
attributes already attached — is simpler for the Planning Team and removes the
chance of two people joining differently.

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

Trade-off: it duplicates dimension attributes and grows with the fact
(`fct_user_disease_day` is ~181k rows and projected to millions per year), so
do it for genuinely repeated joins, not speculatively. The star stays the
source of truth; the wide model is a convenience layer over it.

### Which option to use

| Situation | Use |
|---|---|
| Ongoing self-service for the Planning Team | **A** — set FK metadata once |
| One-off exploration by an analyst | **B** — explicit join |
| The same 3-table join in five saved questions | **C** — pre-join in dbt |
| A number that will be quoted in meetings | A metric view (`v_pi_*`) — see `METRICS.ko.md` |

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
