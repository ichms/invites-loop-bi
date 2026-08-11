-- What superset_reader may read: `marts`, and nothing else.
--
-- Mirror of invites-loop-bi-deploy/sql/02_grants.sql for the Superset role.
-- Run against the WAREHOUSE after 01_superset_reader_role.sql, as the role
-- that owns the marts objects (the dbt user):
--
--   psql "$WAREHOUSE_URI" -f deploy/superset/sql/02_superset_grants.sql
--
-- Idempotent: safe to re-run.

\set ON_ERROR_STOP on

-- 1. The one schema Superset sees.
GRANT USAGE ON SCHEMA marts TO superset_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO superset_reader;

-- 2. Future models, so a new dim/fact never looks like "the dashboard is
--    empty" instead of a permission problem.
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO superset_reader;

-- 3. Explicitly take away everything else. The `public` caveat from the
--    bi_reader script applies verbatim: its USAGE belongs to PUBLIC and cannot
--    be revoked by analytics_user on Azure; the block below proves the
--    residual is harmless instead of assuming it.
REVOKE ALL ON SCHEMA public FROM superset_reader;
REVOKE ALL ON SCHEMA staging FROM superset_reader;
REVOKE ALL ON SCHEMA stg_meta FROM superset_reader;
REVOKE ALL ON SCHEMA stg_iccoli FROM superset_reader;
REVOKE ALL ON SCHEMA stg_sibc FROM superset_reader;
REVOKE ALL ON SCHEMA stg_ichms FROM superset_reader;
REVOKE ALL ON SCHEMA stg_irs FROM superset_reader;
REVOKE ALL ON SCHEMA stg_discovery FROM superset_reader;

-- 4. Prove it rather than assume it.
DO $$
DECLARE
	leaked text;
	public_objects int;
	readable_outside int;
BEGIN
	SELECT string_agg(nspname, ', ' ORDER BY nspname)
	INTO leaked
	FROM pg_namespace
	WHERE nspname NOT IN ('marts', 'public', 'information_schema')
		AND nspname NOT LIKE 'pg_%'
		AND has_schema_privilege('superset_reader', nspname, 'USAGE');

	IF leaked IS NOT NULL THEN
		RAISE EXCEPTION 'superset_reader can reach schemas beyond marts: %', leaked;
	END IF;

	SELECT count(*) INTO public_objects
	FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
	WHERE n.nspname = 'public';

	IF public_objects > 0 THEN
		RAISE EXCEPTION
			'public is no longer empty (% objects) and superset_reader has USAGE on it. Ask an admin for: REVOKE USAGE ON SCHEMA public FROM PUBLIC;',
			public_objects;
	END IF;

	IF has_schema_privilege('superset_reader', 'public', 'CREATE') THEN
		RAISE EXCEPTION 'superset_reader can CREATE in public — it must be read-only everywhere';
	END IF;

	SELECT count(*) INTO readable_outside
	FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
	WHERE c.relkind IN ('r', 'v', 'm', 'f', 'p')
		AND n.nspname NOT IN ('marts', 'information_schema')
		AND n.nspname NOT LIKE 'pg_%'
		AND has_table_privilege('superset_reader', c.oid, 'SELECT');

	IF readable_outside > 0 THEN
		RAISE EXCEPTION 'superset_reader can SELECT from % table(s) outside marts', readable_outside;
	END IF;

	IF NOT has_schema_privilege('superset_reader', 'marts', 'USAGE') THEN
		RAISE EXCEPTION 'superset_reader cannot reach marts — Superset will see nothing';
	END IF;

	RAISE NOTICE 'verified: superset_reader reads marts and nothing else (public is empty and not writable)';
END
$$;
