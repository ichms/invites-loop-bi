# TODO — pick up here

Last updated: **2026-08-07**. Architecture in `CLAUDE.md`; decisions in
`INVITES_LOOP_BI_DECISION_LOG.md`; what measurement overrode in
`IMPLEMENTATION_PLAN.md` §3; handover state in `HANDOVER.md`.

> Replaces the 2026-07-30 version, which predated the transform layer (it still
> described dbt as undecided and the OLAP schema as not started). Recoverable
> in git if any of that context is wanted.

## Where we are

**All five phases are done and committed.** `dbt build` 184/184, `pytest`
117/117. Extract → load → transform → marts → metric views → Metabase all run
**when invoked by hand**. Nothing runs unattended — see §3.

| Piece | State |
|---|---|
| `extract/`, `load/`, `pipeline.py` | done |
| dbt staging (10 views, allow-list + drift test) | done |
| dbt marts — 6 dims, 5 facts, grain + FK tests | done |
| Metric views — 7 `v_pi_*` + `v_bridge_pi_to_kpi` | done |
| Metabase v0.63.5 + `bi_reader` + 3 dashboards | done, local |
| Metabase FK metadata (14 cols) | done 2026-08-07, pushed from dbt |
| PII inventory (Q-11) + cleanup | done; R-7/R-8 open |
| 5 ELT DAGs + `transform_dbt_build` | **written; never run on a schedule** |
| **Named owner (Q-04)** | **deferred — interim only** |

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
