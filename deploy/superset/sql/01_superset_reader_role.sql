-- superset_reader: the role Superset connects to the data warehouse as.
--
-- A PARALLEL of bi_reader (invites-loop-bi-deploy/sql/01_readonly_role.sql),
-- not a replacement: Metabase keeps bi_reader while the Superset/Metabase
-- comparison runs, so neither tool can break the other. Same guarantees:
-- read-only, scoped to `marts` only, no privileged attributes.
--
-- One addition over bi_reader: `timezone = 'Asia/Seoul'`. Metabase solved the
-- KST-midnight problem (D-18) with MB_REPORT_TIMEZONE; Superset has no such
-- setting — its time grains compile to date_trunc() executed in the warehouse
-- session, so the session timezone IS the report timezone. Pinning it on the
-- role makes every GUI date-grouping on a timestamptz column agree with `ymd`.
--
-- Run against the WAREHOUSE (invites_dw), as a role with CREATEROLE:
--
--   psql "$WAREHOUSE_URI" \
--        -v superset_reader_password="$(openssl rand -base64 24)" \
--        -f deploy/superset/sql/01_superset_reader_role.sql
--
-- The password is passed in, never written here. Record it in the password
-- manager and put it in deploy/superset/.env (SS_DW_PASSWORD).
--
-- Idempotent: safe to re-run.

\set ON_ERROR_STOP on

DO $$
BEGIN
	IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
		CREATE ROLE superset_reader LOGIN;
		RAISE NOTICE 'created role superset_reader';
	ELSE
		RAISE NOTICE 'role superset_reader already exists, leaving it in place';
	END IF;
END
$$;

ALTER ROLE superset_reader WITH PASSWORD :'superset_reader_password';

-- Same reasoning as bi_reader: set what CREATEROLE may set, prove the rest.
ALTER ROLE superset_reader NOCREATEROLE NOINHERIT;

DO $$
DECLARE
	r record;
BEGIN
	SELECT rolsuper, rolreplication, rolbypassrls, rolcreatedb, rolcreaterole
	INTO r
	FROM pg_roles WHERE rolname = 'superset_reader';

	IF r.rolsuper OR r.rolreplication OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole THEN
		RAISE EXCEPTION 'superset_reader has privileged attributes it must not have: super=% repl=% bypassrls=% createdb=% createrole=%',
			r.rolsuper, r.rolreplication, r.rolbypassrls, r.rolcreatedb, r.rolcreaterole;
	END IF;

	RAISE NOTICE 'verified: superset_reader holds no privileged role attributes';
END
$$;

-- Read-only at the transaction level, not just by grants.
ALTER ROLE superset_reader SET default_transaction_read_only = on;

-- SQL Lab invites exploratory queries even more than Metabase's GUI does;
-- a runaway one dies rather than holding warehouse resources. Matches
-- SQLLAB_TIMEOUT in superset_config.py — keep the two in sync.
ALTER ROLE superset_reader SET statement_timeout = '120s';
ALTER ROLE superset_reader SET idle_in_transaction_session_timeout = '60s';

-- D-18 equivalent (see header): KST is decided here, not in chart settings.
ALTER ROLE superset_reader SET timezone = 'Asia/Seoul';

GRANT CONNECT ON DATABASE invites_dw TO superset_reader;
