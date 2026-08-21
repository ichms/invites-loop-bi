-- P2 physical boundary migration. Run against invites_dw as analytics_user.
--
-- This does not rebuild, truncate, or delete data. It creates the private and
-- detail schemas, then moves seven existing relations in-place:
--   * six empty source-grain wearable fact tables: marts -> marts_detail
--   * the populated reusable wearable-day aggregate: staging ->
--     intermediate_private
--
-- Idempotent and fail-closed: a destination collision or an unexpected
-- relation location raises before commit.

\set ON_ERROR_STOP on

BEGIN;

CREATE SCHEMA IF NOT EXISTS intermediate_private AUTHORIZATION analytics_user;
CREATE SCHEMA IF NOT EXISTS marts_detail AUTHORIZATION analytics_user;

DO $$
DECLARE
	relation_name text;
	source_relation regclass;
	destination_relation regclass;
BEGIN
	FOREACH relation_name IN ARRAY ARRAY[
		'fct_wearable_activity',
		'fct_wearable_heartrate',
		'fct_wearable_oxygen_saturation',
		'fct_wearable_sleep',
		'fct_wearable_sleep_stage',
		'fct_wearable_step'
	]
	LOOP
		source_relation := to_regclass(format('marts.%I', relation_name));
		destination_relation := to_regclass(format('marts_detail.%I', relation_name));

		IF source_relation IS NOT NULL AND destination_relation IS NOT NULL THEN
			RAISE EXCEPTION 'both source and destination exist for %', relation_name;
		ELSIF source_relation IS NOT NULL THEN
			EXECUTE format('ALTER TABLE marts.%I SET SCHEMA marts_detail', relation_name);
		ELSIF destination_relation IS NULL THEN
			RAISE EXCEPTION '% exists in neither marts nor marts_detail', relation_name;
		END IF;
	END LOOP;

	source_relation := to_regclass('staging.stg_discovery__lifelog_wearable_day');
	destination_relation := to_regclass(
		'intermediate_private.stg_discovery__lifelog_wearable_day'
	);

	IF source_relation IS NOT NULL AND destination_relation IS NOT NULL THEN
		RAISE EXCEPTION 'both source and destination wearable-day relations exist';
	ELSIF source_relation IS NOT NULL THEN
		ALTER TABLE staging.stg_discovery__lifelog_wearable_day
			SET SCHEMA intermediate_private;
	ELSIF destination_relation IS NULL THEN
		RAISE EXCEPTION 'wearable-day relation exists in neither staging nor intermediate_private';
	END IF;
END
$$;

DO $$
DECLARE
	detail_count integer;
	marts_leak_count integer;
BEGIN
	SELECT count(*)
	INTO detail_count
	FROM pg_class c
	JOIN pg_namespace n ON n.oid = c.relnamespace
	WHERE n.nspname = 'marts_detail'
		AND c.relkind IN ('r', 'p')
		AND c.relname IN (
			'fct_wearable_activity',
			'fct_wearable_heartrate',
			'fct_wearable_oxygen_saturation',
			'fct_wearable_sleep',
			'fct_wearable_sleep_stage',
			'fct_wearable_step'
		);

	SELECT count(*)
	INTO marts_leak_count
	FROM pg_class c
	JOIN pg_namespace n ON n.oid = c.relnamespace
	WHERE n.nspname = 'marts'
		AND c.relname LIKE 'fct_wearable_%'
		AND c.relname <> 'fct_wearable_day';

	IF detail_count <> 6 THEN
		RAISE EXCEPTION 'expected six wearable detail relations, found %', detail_count;
	END IF;

	IF marts_leak_count <> 0 THEN
		RAISE EXCEPTION 'found % wearable detail relation(s) in marts', marts_leak_count;
	END IF;

	IF to_regclass('intermediate_private.stg_discovery__lifelog_wearable_day') IS NULL THEN
		RAISE EXCEPTION 'private wearable-day relation is absent';
	END IF;
END
$$;

COMMIT;
