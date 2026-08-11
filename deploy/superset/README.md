# Superset deploy

Apache Superset (pinned 6.1.0) — the BI viewer for the `invites_dw` warehouse.
It connects as `superset_reader`: read-only, scoped to the `marts` schema and
nothing else, with the session timezone pinned to Asia/Seoul at the role.
Runs on a laptop with nothing but Docker (Colima), server on **:8088**.

## Bring-up

```bash
cd deploy/superset
cp .env.example .env            # fill in secrets (see comments in the file)

# once, against the warehouse (role + grants; idempotent):
psql "$WAREHOUSE_URI" -v superset_reader_password="$SS_DW_PASSWORD" -f sql/01_superset_reader_role.sql
psql "$WAREHOUSE_URI" -f sql/02_superset_grants.sql

docker-compose up -d            # init service bootstraps, then the server starts
./scripts/register_marts_datasets.sh   # marts tables/views → Superset datasets
./scripts/build_pi_dashboard.py        # PI dashboard (charts + layout) as code
```

Login at http://localhost:8088 with `SS_ADMIN_USER` / `SS_ADMIN_PASSWORD`.
The PI dashboard lands at `/superset/dashboard/pi-metrics/` — charts, layout
and the METRICS.ko.md interpretation rules are all created by
`build_pi_dashboard.py`, so the dashboard is reproducible from git.
Re-running it rewrites the layout; UI edits to these charts do not survive,
by design (same rule as "metrics live in git, not in dashboard cards").

## The pieces, and why they are shaped this way

| Piece | Rationale |
|---|---|
| `superset-app-db` (postgres:17) | Superset's own storage: dashboards, users, encrypted warehouse credentials. Named volume — the one thing here that is real data. Never the SQLite default (D-13). Matches the warehouse major version so there is one Postgres idiom to learn. |
| `superset-init` (one-shot) | Migrates the app DB, ensures the admin user, registers the warehouse connection with `set-database-uri` — the whole bootstrap is config, not clicks, and idempotent on every `up`. |
| `Dockerfile` | Upstream ships no DB drivers at all; the derived image adds `psycopg2-binary`. Version bumps happen here (change the `FROM` tag, back up first, no downgrades). |
| `superset_reader` role | The PII boundary. Read-only at the transaction level, marts-only by grant, **proved** by the verification block in `sql/02_superset_grants.sql` rather than assumed. |
| `ALTER ROLE ... SET timezone = 'Asia/Seoul'` | `ymd` is a business date on a KST midnight boundary (D-18). Superset's time grains compile to `date_trunc()` in the warehouse session, so the session timezone IS the report timezone — it is enforced at the role, not in chart settings. |
| Explicit datasets | Superset does not schema-sync. New dbt models become visible by re-running `register_marts_datasets.sh`; permissions need nothing (default privileges cover new marts objects). |
| `SUPERSET_SECRET_KEY` | Encrypts stored warehouse credentials at rest. Changing it orphans every stored secret — keep it with the backups. |

Timeouts are set in two places on purpose: the role kills runaway queries
(`statement_timeout = 120s`) and `SQLLAB_TIMEOUT` matches it so the UI stops
waiting when the database has already given up. Keep the two in sync.

## Backups

The app DB named volume (`superset_app_db_data`) is the only real state.
`pg_dump` it from inside the network (the port is deliberately not published):

```bash
docker exec superset-app-db pg_dump -U superset -Fc superset_app > backups/superset_app_$(date +%Y%m%d).dump
```

A restore drill — performed, not merely scripted — is still an open handover
item (HANDOVER.md #4), as is a Korean runbook (#6).
