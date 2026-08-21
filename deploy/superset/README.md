# Superset local deployment

This directory defines a local Apache Superset 6.1.0 stack for exploring the
`invites_dw` warehouse. It is a development deployment on Colima, not a
production service or scheduler.

## Current state — 2026-08-21

Superset must not be treated as a source of current operating numbers:

- P3 targeted builds populated redesigned core relations, but no Superset
  refresh or representative-chart acceptance was run;
- the existing PI views and dashboard remain unaccepted legacy definitions;
- the W-A/B/C/D semantic layer and metric registry do not exist yet;
- P2 moved source-grain wearable facts to `marts_detail` and reusable physical
  aggregation to `intermediate_private`; P4 heart-rate reuse is implemented,
  while detail remains unbuilt without a named consumer;
- registration discovers only `marts` and fails closed if a known detail fact
  drifts back into that schema;
  and
- no production host, automatic dbt schedule, durable operating owner, or
  failure-notification path has been established.

Do not register all current marts datasets or rebuild the legacy PI dashboard.
Dataset and dashboard work resumes in P6 only after the core/detail boundary,
freshness gate, storage gate, tests, and reader-role verification pass. See
[`todo.md`](../../todo.md).

## Components

| Component | Responsibility | State |
|---|---|---|
| `superset` | Local web application on port 8088 by default | Reproducible container, not production-hosted |
| `superset-init` | Migrates the application DB, creates the initial admin, and optionally registers a warehouse connection | Local bootstrap only |
| `superset-app-db` | Superset metadata: users, roles, datasets, charts, dashboards, and encrypted connection credentials | Persistent named volume; backup owner unresolved |
| `superset_reader` | Read-only PostgreSQL login used by Superset | P2 verified live `marts` access plus denial of `marts_detail`, `intermediate_private`, staging, and landing; repeat after P6 recovery |
| Dashboard builder | Recreates the legacy PI dashboard from code | Must be revised for W-A/B/C/D before P6 use |

The application metadata volume is real state even when a dashboard can be
recreated from code. `SUPERSET_SECRET_KEY` is separate critical state because
it protects stored credentials; losing or changing it makes those credentials
unusable.

## Local prerequisites

The container engine on this machine is Colima. The full local workflow also
uses the Docker CLI with Compose, PostgreSQL `psql`, `curl`, and Python 3 for
the existing helper scripts. Docker Desktop is not part of this setup.

Copy `.env.example` to the gitignored `.env` and provide local secrets before
starting the stack. Use URI-safe passwords for database credentials unless the
connection-building code is changed to percent-encode them; unencoded `/`, `@`,
or `:` characters can break a SQLAlchemy URI. `SUPERSET_SECRET_KEY` is not a
database password and must be backed up separately.

The local application containers can be started with:

```bash
cd deploy/superset
docker compose up -d
```

This starts the local application only. It does not make the warehouse marts
correct, register approved datasets, validate access boundaries, or create a
production deployment.

## Warehouse role provisioning

The SQL files have different privilege requirements and must be run only by an
authorised warehouse operator:

- `sql/01_superset_reader_role.sql` requires a connection allowed to create or
  alter the login role;
- `sql/02_superset_grants.sql` must run as the role that owns the dbt-created
  relations, because default privileges apply to objects created by that role.

`WAREHOUSE_URI` is not a setting in `.env.example`, and the
`superset_reader` connection itself is not privileged enough to perform these
steps. Do not paste a warehouse role password into shell history or assume that
re-running role DDL is a harmless read-only operation.

The database role provides a schema and transaction boundary. It is not, by
itself, the entire PII control. Extraction exclusions, staging/mart PII tests,
core/detail placement, and an actual negative-access test are also required.

The repository does not currently provision a Superset application role for a
Planning Team or prove that SQL Lab is disabled for one. Do not claim those UI
permissions exist until a named application role is created, tested, and
documented.

## P2 and P6 exposure gates

No core dataset may be exposed to Superset until all of these conditions hold:

1. `marts` contains core and serving relations only.
2. Source-grain wearable facts are in `marts_detail`.
3. Reusable physical intermediates are outside every general BI role.
4. `superset_reader` has `USAGE` and `SELECT` only where intended and has no
   access to landing, staging, physical intermediates, or `marts_detail`.
5. The dataset-registration path discovers or allow-lists core relations only.
6. Required source freshness passes as a hard gate.
7. Azure Monitor storage is below the 80% stop line immediately before the
   single-threaded `daily_core` build.
8. The complete selected core graph, including grain, FK, PII, panel, metric,
   and freshness tests, is green.
9. Public metrics include evidence status and `data_as_of`.
10. Dashboard code no longer references retired or renamed legacy metrics.

After those gates pass, test the role through the same connection Superset will
use. A grant file that looks correct is not proof of denial. Dataset
registration and dashboard creation are P6 release actions, not local bring-up
steps.

## Time and query safeguards

Business dates use the `Asia/Seoul` boundary. The warehouse role pins its
session timezone because Superset time grains execute in the warehouse
session. The role also applies a 120-second statement timeout, matched by the
Superset web configuration.

These timeouts limit individual queries; they do not make high-cost wearable
detail suitable for a general dashboard. `marts_detail` remains outside the
general reader role, and detail builds require their own Azure Monitor,
single-thread, and stop procedure.

## Metrics and dashboards

Metric definitions belong in git-tracked dbt views and a versioned registry,
not in ad hoc dashboard expressions. The target dashboard must distinguish
`OBSERVED`, `DERIVED`, `HYPOTHESIS`, and `ROADMAP`, display the last successful
EL/build time, and expose the denominator and freshness context needed to read
each result.

The current dashboard builder contains the legacy chart inventory and Korean
labels. It is reproducible code, but reproducibility does not make its metric
semantics current. Revise it only after P5 settles view disposition and P6 has
a green core. See [`METRICS.md`](METRICS.md) for the analyst contract.

## Backup and recovery

Back up all of the following together:

- the Superset application PostgreSQL database;
- `SUPERSET_SECRET_KEY`;
- the environment-specific connection and administrator secrets in the
  approved secret store; and
- the exact Superset image/config version needed for restore.

Do not write metadata dumps into an unignored directory inside the repository.
Use a protected backup location outside the worktree, encrypt it as required,
and perform a restore drill before calling the deployment recoverable.

The durable backup location, retention, restore operator, metadata-DB owner,
and secret-rotation procedure remain P7 decisions. Until they are assigned, the
local app database is development state rather than a production dependency.

## Production boundary

Production hosting is not a prerequisite for mart correctness, but a local
laptop cannot be an operating component. Before automatic operation, P7 must
establish the EL-to-transform dependency, hard freshness and storage preflight,
durable Airflow and Superset metadata storage, service identity, backup and
restore ownership, and failure notifications. A fixed 01:00/02:00 time gap is
not a dependency contract.
