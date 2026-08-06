# TODO — pick up here

Last updated: **2026-08-06**. Architecture in `CLAUDE.md`; decisions in
`INVITES_LOOP_BI_DECISION_LOG.md`; what measurement overrode in
`IMPLEMENTATION_PLAN.md` §3; handover state in `HANDOVER.md`.

> Replaces the 2026-07-30 version, which predated the transform layer (it still
> described dbt as undecided and the OLAP schema as not started). Recoverable
> in git if any of that context is wanted.

## Where we are

**All five phases are done and committed.** `dbt build` 184/184, `pytest`
117/117. Extract → load → transform → marts → metric views → Metabase all run.

| Piece | State |
|---|---|
| `extract/`, `load/`, `pipeline.py`, 5 ELT DAGs | done; scheduled 01:00 KST |
| dbt staging (10 views, allow-list + drift test) | done |
| dbt marts — 6 dims, 5 facts, grain + FK tests | done |
| Metric views — 7 `v_pi_*` + `v_bridge_pi_to_kpi` | done |
| `transform_dbt_build` DAG | done; 02:00 KST, `--fail-fast` |
| Metabase v0.63.5 + `bi_reader` + 3 dashboards | done, local |
| PII inventory (Q-11) + cleanup | done; R-7/R-8 open |
| **Named owner (Q-04)** | **deferred — interim only** |

Session ended because we went off the corporate network and the Azure
warehouse became unreachable.

---

## Blocked on corporate network access

### 1. Finish the dbt-metabase sync — the FK metadata gap

**Why it matters:** Metabase infers joins from database foreign-key
constraints. dbt creates none, so Metabase sees eleven unrelated tables and
**cross-table filtering is unavailable in the query builder**. Measured today:
**0 of 21 key columns carry FK metadata.**

`dbt-metabase` reads `dbt/target/manifest.json` and pushes descriptions and FK
relationships into Metabase's Table Metadata over the API. It **infers foreign
keys from native dbt `relationships` tests** — and all 14 of ours are already
declared in `marts.yml`, so the FK graph is in git and only needs pushing.

Done: `dbt-metabase==1.7.5` added to the `transform` group (uncommitted — §5).

**Where it stopped:** the tool's pre-flight `POST /api/database/2/sync_schema`
returned `422 — Timed out after 10.0 s`. Not a dbt-metabase bug: that call makes
Metabase connect to the Azure warehouse, which fails off-network. Confirmed by
calling the endpoint directly with both an API key and an admin session —
identical timeout.

On-network:

```bash
source setup_env.sh
uv run dbt parse --project-dir dbt --no-partial-parse    # refresh manifest.json
# create a short-lived admin API key: Admin → Settings → Authentication → API keys
uv run dbt-metabase models \
  --manifest-path dbt/target/manifest.json \
  --metabase-url http://localhost:3000 \
  --metabase-api-key "$KEY" \
  --metabase-database "Invites Loop DW (marts)" \
  --include-schemas marts
```

`--sync-timeout 0` skips the pre-flight sync if it still fails (the schema is
already in sync, so that is safe).

**Verify** — should report 14, not 0:

```bash
curl -s -H "X-Metabase-Session: $SESSION" http://localhost:3000/api/database/2/metadata \
 | python3 -c "import json,sys; print(sum(1 for t in json.load(sys.stdin)['tables'] for f in t['fields'] if f.get('semantic_type')=='type/FK'), 'FK columns')"
```

**Acceptance test** — the thing that prompted all this: build a question on
`fct_user_disease_day` and filter by `dim_disease.phenotype_kor` **and**
`dim_user.sex` at once, without writing SQL.

Delete the API key afterwards (none exist in the instance right now).

### 2. Rewrite `HOWTO.md` §3 Option A

It documents the manual UI/API route for the 14 FK relationships. Once
dbt-metabase is proven, lead with it and keep the manual route as fallback —
the mapping table stays useful as a statement of what should exist. The point
worth recording: FK metadata then lives in `marts.yml` and ships from git,
rather than as undocumented clicks in a UI.

### 3. Confirm the first scheduled DAG runs

Schedules were set today and have not fired yet (ELT 01:00 KST,
`transform_dbt_build` 02:00 KST). Check the first runs succeeded and
`dbt source freshness` is clean — several sources will WARN until the DAGs have
actually run on schedule.

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

### 5. Commit or back out the dbt-metabase dependency

`pyproject.toml` and `uv.lock` are modified but uncommitted on purpose — the
tool is not yet proven here. Commit once §1 succeeds, or
`git checkout pyproject.toml uv.lock` to drop it.

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
| Q-13 production hosting | Deliberately deferred; everything is hosting-independent |

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
- All test API keys deleted; probe collection archived. No API keys currently
  exist in the instance.
- Last verified backup restore: 2026-08-06 post-upgrade — 178 tables,
  5 dashboards, 11 questions, 5 permission groups into a scratch container.
