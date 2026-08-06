-- One-time warehouse cleanup #2, 2026-08-06 (Phase 1 / Q-11 inventory follow-up).
--
-- The Q-11 inventory (PII_INVENTORY.md) found direct identifiers the Phase 0
-- pruning missed. The owner decided (2026-08-06) to discard the flagrant
-- classes — credential material, phone numbers, names, birth dates, login IPs,
-- the medical chart number — plus same-class items (device push tokens, login
-- ids, session-token ids, photo URL, free-text family messages). The extraction
-- configs now exclude every column dropped here, so schema evolution (which
-- only re-ADDs columns introspection reports) cannot bring them back.
--
-- Everything removed remains in the operational source systems and is
-- re-extractable after a config + watermark change if a decision is reversed.
-- Run as: psql service=invites_dw -f scripts/20260806_pii_cleanup_phase1.sql

BEGIN;

-- ichms: identity/auth layer, not cohort-filtered (~16k accounts).
ALTER TABLE stg_ichms.auth_user
	DROP COLUMN IF EXISTS user_tel;
ALTER TABLE stg_ichms.auth_user_account
	DROP COLUMN IF EXISTS login_id,
	DROP COLUMN IF EXISTS login_pw;
ALTER TABLE stg_ichms.auth_user_login_history
	DROP COLUMN IF EXISTS login_ip,
	DROP COLUMN IF EXISTS token_id;
ALTER TABLE stg_ichms.auth_user_profile
	DROP COLUMN IF EXISTS user_name,
	DROP COLUMN IF EXISTS user_birth;
ALTER TABLE stg_ichms.auth_user_withdraw_history
	DROP COLUMN IF EXISTS user_tel;
ALTER TABLE stg_ichms.mem_family
	DROP COLUMN IF EXISTS family_name;
ALTER TABLE stg_ichms.mem_family_msg
	DROP COLUMN IF EXISTS msg_cn;
ALTER TABLE stg_ichms.mem_user
	DROP COLUMN IF EXISTS chart_no,
	DROP COLUMN IF EXISTS profile_img_url;

-- sibc: relational name / DOB columns (D-22/D-23 said "never selected";
-- the owner decision upgrades that to "never landed").
ALTER TABLE stg_sibc.target_calorie
	DROP COLUMN IF EXISTS user_name;
ALTER TABLE stg_sibc.user_master
	DROP COLUMN IF EXISTS user_nm,
	DROP COLUMN IF EXISTS birthday,
	DROP COLUMN IF EXISTS birthtime;
ALTER TABLE stg_sibc.user_profiles_log
	DROP COLUMN IF EXISTS user_name;

-- iccoli: token + phone + username columns the Phase 0 pass missed.
ALTER TABLE stg_iccoli.tb_loop_push_history
	DROP COLUMN IF EXISTS push_token;
ALTER TABLE stg_iccoli.tb_point_item_cpn_issue_intr_hist
	DROP COLUMN IF EXISTS call_ctn,
	DROP COLUMN IF EXISTS rcv_ctn;
ALTER TABLE stg_iccoli.tb_point_item_cpn_state_intr_hist
	DROP COLUMN IF EXISTS call_ctn,
	DROP COLUMN IF EXISTS rcv_ctn;
ALTER TABLE stg_iccoli.tb_user_info
	DROP COLUMN IF EXISTS id,
	DROP COLUMN IF EXISTS nickname,
	DROP COLUMN IF EXISTS sub_nickname,
	DROP COLUMN IF EXISTS introduce;

-- Name keys embedded in FROZEN legacy jsonb (both stopped being written
-- 2026-03-06, so a one-time strip is durable). The live payload's user_name
-- key (user_intg_log.intg_anlys) is NOT stripped here: it is re-landed with
-- every new row, so warehouse-side stripping cannot stick — it is guarded by
-- the D-26 allow-list (never extracted) and its removal belongs upstream.
UPDATE stg_sibc.user_irs_log
SET irs_data = irs_data - 'USERNAME'
WHERE jsonb_typeof(irs_data) = 'object' AND irs_data ? 'USERNAME';

UPDATE stg_sibc.user_profiles_log
SET irs_data = irs_data - 'USERNAME'
WHERE jsonb_typeof(irs_data) = 'object' AND irs_data ? 'USERNAME';

UPDATE stg_sibc.user_profiles_log
SET health_profile = health_profile - 'user_name'
WHERE jsonb_typeof(health_profile) = 'object' AND health_profile ? 'user_name';

COMMIT;
