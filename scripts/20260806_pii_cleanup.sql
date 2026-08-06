-- One-time warehouse cleanup, 2026-08-06 (IMPLEMENTATION_PLAN.md N-01 / N-02).
--
-- The extraction config now (a) excludes direct-identifier columns at the
-- source (`exclude_columns`) and (b) restricts every user-keyed iccoli table to
-- Loop-cohort accounts (`row_filter` = LOOP_USERS_ONLY). This script brings the
-- already-landed staging data in line with that policy:
--
--   1. drops the landed copy of tables that are no longer targets,
--   2. drops the landed copies of excluded columns,
--   3. deletes community-user rows that predate the row filter.
--
-- Everything removed here remains in the operational source systems; if a
-- scope decision ever changes, delete the affected iccoli rows from
-- stg_meta.watermarks and the next run re-extracts under the then-current
-- config. Run as: psql service=invites_dw -f scripts/20260806_pii_cleanup.sql

BEGIN;

-- 1. tb_ext_user_preinfo is no longer an extraction target (pre-registration
--    identity: name, phone, birth).
DROP TABLE IF EXISTS stg_iccoli.tb_ext_user_preinfo;
DELETE FROM stg_meta.watermarks
WHERE source_system = 'iccoli' AND schema_name = 'public' AND table_name = 'tb_ext_user_preinfo';

-- 2. Excluded columns (see iccoli_targets.py). Schema evolution only ever ADDs
--    columns the introspection reports, and introspection no longer sees these,
--    so they stay gone.
ALTER TABLE stg_iccoli.tb_user_personal_info
	DROP COLUMN IF EXISTS ci,
	DROP COLUMN IF EXISTS di,
	DROP COLUMN IF EXISTS name,
	DROP COLUMN IF EXISTS phone,
	DROP COLUMN IF EXISTS email,
	DROP COLUMN IF EXISTS telecom;

ALTER TABLE stg_iccoli.tb_user_device_info
	DROP COLUMN IF EXISTS device_token,
	DROP COLUMN IF EXISTS game_token,
	DROP COLUMN IF EXISTS apns_push_to_start_token,
	DROP COLUMN IF EXISTS apns_la_token,
	DROP COLUMN IF EXISTS la_activity_id,
	DROP COLUMN IF EXISTS device_id;

-- 3. Community-user rows loaded before the row filter existed. Same predicate
--    the extractor now applies at the source, replayed against the landed copy.
DELETE FROM stg_iccoli.tb_user_login_log t         WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_user_personal_info t     WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_user_info t              WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_activity_user_log t      WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_action_user_log t        WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_loop_push_history t      WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_message_send_hist t      WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_stats_avg_login_cnt_log t WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_user_activity_info t     WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_user_attendance t        WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_user_device_info t       WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_stats_menu_visit_log t   WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_point_item_srch_hist_log t WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_point_user_dtl t         WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');
DELETE FROM stg_iccoli.tb_point_user_adj_hist t    WHERE NOT EXISTS (SELECT 1 FROM stg_iccoli.tb_ext_user_mapper m WHERE m.user_no = t.user_no AND m.ext_system_code = 'LOOP');

COMMIT;
