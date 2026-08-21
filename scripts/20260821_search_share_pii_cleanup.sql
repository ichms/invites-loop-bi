-- One-time P0 cleanup for the iccoli search/share landing tables.
--
-- The extraction config excludes these fields before COPY after this change:
--
--   stg_iccoli.tb_search_log.word
--   stg_iccoli.tb_share_info.share_key
--   stg_iccoli.tb_share_log.share_key
--   stg_iccoli.tb_share_log.to_user_ip
--   stg_iccoli.tb_share_log.to_user_agent
--   stg_iccoli.tb_share_log.to_user_no
--
-- This migration removes any already-landed copies. It deliberately keeps
-- tb_share_info.target_no: that polymorphic key is restricted from general
-- marts by the dbt projection contract, pending per-share-type review.
--
-- Executed successfully on 2026-08-21 KST after dependency review. Retain as
-- migration evidence and do not rerun blindly. It must never be combined with
-- an EL run, landing truncation, row deletion, or watermark change.
-- Reviewed command:
--   psql service=invites_dw -v ON_ERROR_STOP=1 \
--     -f scripts/20260821_search_share_pii_cleanup.sql

BEGIN;

-- Abort if a warehouse view has acquired a dependency on a prohibited column
-- since the 2026-08-21 read-only preflight. DROP COLUMN also uses RESTRICT, but
-- this guard reports the affected relation before any ALTER TABLE runs.
DO $$
BEGIN
	IF EXISTS (
		SELECT 1
		FROM pg_depend d
		JOIN pg_class src ON src.oid = d.refobjid
		JOIN pg_namespace src_ns ON src_ns.oid = src.relnamespace
		JOIN pg_attribute attr
			ON attr.attrelid = src.oid
			AND attr.attnum = d.refobjsubid
		JOIN pg_rewrite rw ON rw.oid = d.objid
		JOIN pg_class dep ON dep.oid = rw.ev_class
		WHERE src_ns.nspname = 'stg_iccoli'
			AND (
				(src.relname = 'tb_search_log' AND attr.attname = 'word')
				OR (src.relname = 'tb_share_info' AND attr.attname = 'share_key')
				OR (
					src.relname = 'tb_share_log'
					AND attr.attname IN ('share_key', 'to_user_ip', 'to_user_agent', 'to_user_no')
				)
			)
			AND dep.oid <> src.oid
	) THEN
		RAISE EXCEPTION 'search/share PII cleanup blocked: a prohibited landing column has a dependent view';
	END IF;
END
$$;

ALTER TABLE stg_iccoli.tb_search_log
	DROP COLUMN IF EXISTS word RESTRICT;

ALTER TABLE stg_iccoli.tb_share_info
	DROP COLUMN IF EXISTS share_key RESTRICT;

ALTER TABLE stg_iccoli.tb_share_log
	DROP COLUMN IF EXISTS share_key RESTRICT,
	DROP COLUMN IF EXISTS to_user_ip RESTRICT,
	DROP COLUMN IF EXISTS to_user_agent RESTRICT,
	DROP COLUMN IF EXISTS to_user_no RESTRICT;

-- Fail the transaction if a prohibited field survives. This also catches a
-- misspelled table or column in the ALTER statements above.
DO $$
BEGIN
	IF EXISTS (
		SELECT 1
		FROM information_schema.columns
		WHERE table_schema = 'stg_iccoli'
			AND (
				(table_name = 'tb_search_log' AND column_name = 'word')
				OR (table_name = 'tb_share_info' AND column_name = 'share_key')
				OR (
					table_name = 'tb_share_log'
					AND column_name IN ('share_key', 'to_user_ip', 'to_user_agent', 'to_user_no')
				)
			)
	) THEN
		RAISE EXCEPTION 'search/share PII cleanup failed: prohibited landing columns remain';
	END IF;

	IF NOT EXISTS (
		SELECT 1
		FROM information_schema.columns
		WHERE table_schema = 'stg_iccoli'
			AND table_name = 'tb_share_info'
			AND column_name = 'target_no'
	) THEN
		RAISE EXCEPTION 'search/share PII cleanup failed: retained target_no is missing';
	END IF;
END
$$;

COMMIT;

-- Human-readable postcondition. Expected result: zero rows.
SELECT table_schema, table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'stg_iccoli'
	AND (
		(table_name = 'tb_search_log' AND column_name = 'word')
		OR (table_name = 'tb_share_info' AND column_name = 'share_key')
		OR (
			table_name = 'tb_share_log'
			AND column_name IN ('share_key', 'to_user_ip', 'to_user_agent', 'to_user_no')
		)
	)
ORDER BY table_name, column_name;

-- Expected result: the three grain candidates, two actor keys, share parent FK,
-- polymorphic target key, timestamps, and loader metadata all remain.
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'stg_iccoli'
	AND table_name IN ('tb_search_log', 'tb_share_info', 'tb_share_log')
ORDER BY table_name, ordinal_position;
