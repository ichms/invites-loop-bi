# Superset deploy (migration/superset branch)

Apache Superset 6.1.0 against the same warehouse as the Metabase stack in
`invites-loop-bi-deploy`, run side by side for a tool comparison
(owner decision 2026-08-11). Superset on **:8088**, Metabase keeps :3000.
Neither touches the other: Superset connects as its own `superset_reader`
role (marts-only, read-only), Metabase keeps `bi_reader`.

## Bring-up

```bash
cd deploy/superset
cp .env.example .env            # fill in secrets (see comments in the file)

# once, against the warehouse (role + grants; idempotent):
psql "$WAREHOUSE_URI" -v superset_reader_password="$SS_DW_PASSWORD" -f sql/01_superset_reader_role.sql
psql "$WAREHOUSE_URI" -f sql/02_superset_grants.sql

docker compose up -d            # init service bootstraps, then the server starts
./scripts/register_marts_datasets.sh   # marts tables/views → Superset datasets
```

Login at http://localhost:8088 with `SS_ADMIN_USER` / `SS_ADMIN_PASSWORD`.

## How this maps to the Metabase deploy

| Concern | Metabase (`invites-loop-bi-deploy`) | Superset (here) |
|---|---|---|
| App DB | `metabase-app-db` (postgres:17) | `superset-app-db` (postgres:17) |
| Warehouse role | `bi_reader` | `superset_reader` (parallel, same guarantees) |
| KST report dates (D-18) | `MB_REPORT_TIMEZONE=Asia/Seoul` | `ALTER ROLE ... SET timezone` — Superset has no report-timezone setting |
| Warehouse connection | UI only (OSS limitation) | `superset set-database-uri` in the init service — config, not clicks |
| Tables visible to users | automatic schema sync | explicit datasets (`register_marts_datasets.sh`); new dbt models need a re-run |
| Version policy | current line, ~2-month EOL treadmill | pinned 6.1.0; slower release train |
| Secrets at rest | `MB_ENCRYPTION_SECRET_KEY` | `SUPERSET_SECRET_KEY` (same "changing it orphans credentials" rule) |

## Backups

Same principle as the Metabase runbook: the app DB named volume
(`superset_app_db_data`) is the only real state. `pg_dump` it the same way
`scripts/backup.sh` does in the deploy repo; a Superset-specific script can be
copied over once the comparison decides anything is worth keeping.
