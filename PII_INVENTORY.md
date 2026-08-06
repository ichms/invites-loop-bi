# PII Inventory — Q-11 (all five landing schemas)

**Date:** 2026-08-06 (all counts measured this day against `invites_dw`)
**Scope:** every column of every table in `stg_iccoli`, `stg_sibc`, `stg_ichms`, `stg_irs`,
`stg_discovery` — 123 tables, 1,246 columns — enumerated from
`information_schema.columns` and classified below. This is the Q-11 deliverable the decision
log asked for ("the difference between a policy and a belief").
**Placement note:** the implementation plan named `analysis/pii_inventory.md`, but `analysis/`
is gitignored as local scratch; a handover deliverable (log §5) must be versioned, so it lives
here at the repo root.

## Classification scheme

| Class | Meaning |
|---|---|
| **direct** | Identifies a person on its own (name, phone, login id, device/push token, IP, medical chart number, credential material) |
| **quasi** | Identifying in combination at n≈400–1,300 (birth date/year, age, sex, height/weight, birthplace, nationality, race, family linkage, referral codes) |
| **sensitive** | Special-category *content*: clinical narrative, free-text health chat, genomic data, prescriptions, consultation records — regardless of whether it names anyone |
| **key** | Pseudonymous join keys (`user_id` uuid, `user_no`, `*_sn`, `*_no`, thread/msg ids). Identifying only via linkage; they are the analytical backbone and stay |
| **analytical / meta** | Everything else: measures, codes, flags, timestamps, `_loaded_at` bookkeeping |

Columns not named in a table's row below are **analytical/meta** — the partition is complete.

## Headline findings (ordered by severity)

1. **Credential material in the warehouse.** `stg_ichms.auth_user_account.login_pw` holds
   16,184 bcrypt hashes (`$2…`, len 60). Hashed or not, password hashes have zero analytical
   value and make the warehouse an attack target. → R-5, most urgent single item.
2. **iCHMS is an unminimised identity layer** (the Q-11 worry, confirmed): `auth_user.user_tel`
   (575/578 rows), `auth_user_profile.user_name` + `user_birth`, `auth_user_login_history.login_ip`,
   `auth_user_withdraw_history.user_tel`, `mem_user.chart_no` (medical record number) +
   `profile_img_url`, `mem_family.family_name`, `mem_family_msg.msg_cn` (free-text family
   messages). Note iCHMS is **not cohort-filtered** — these are ~16k accounts, far beyond the
   404-user cohort. No planned mart reads any of it. → R-5.
3. **`tb_loop_push_history.push_token`: 236,008 rows, all non-null.** N-01 pruned device
   tokens from `tb_user_device_info` but missed this table. → R-2.
4. **Phone numbers in the coupon SMS trail.** `tb_point_item_cpn_issue_intr_hist` and
   `tb_point_item_cpn_state_intr_hist` carry `call_ctn` / `rcv_ctn` (11-digit, all-numeric —
   phone-number shaped; 714 rows) plus `sender`, `receiver`, `send_msg` (SMS content). → R-3.
5. **Names in sibc relational columns**: `target_calorie.user_name` (404 rows),
   `user_profiles_log.user_name` (476 rows), `user_master.user_nm` — alongside
   `user_master.birthday`/`birthtime` (full DOB+time) and static `age`/`bio_age`. dbt staging
   never selects them (D-22/D-23), but they land and sit reachable by any warehouse
   credential. → R-4.
6. **Names inside JSONB**: `user_intg_log.intg_anlys` top-level `user_name` key (drift-guarded,
   never extracted); `user_irs_log.irs_data` legacy object-form rows (467 rows,
   2025-12→2026-03) with `USERNAME`, `1_AGE`, `WEIGHT`, `BiologicalAGE` keys;
   `stg_irs.irs_data` / `irs_data_log.raw_data` are the upstream of the same payload
   (content not exhaustively audited — assume same). → R-4/R-6.
7. **Genomic/clinical payload sprawl**: `stg_irs.job_input_data.genotype` (5,787 rows) +
   `medical`/`profile`/`lifestyle`/`merged_data`/`result_data`; `stg_sibc.user_dtc_log`,
   `chat_msgs`, `user_guardrail.patient_summary`; `stg_discovery` consultation / examination /
   medical / prescription / dtc / genomic payloads. Purpose-aligned but must never reach
   marts raw; several feed no planned model at all. → R-6/R-7.

## Resolution status (owner decision, same day — 2026-08-06)

The owner decided to **discard** the direct-identifier classes above (credential
material, phone numbers, names, birth dates, login IPs, chart number) and left
same-class judgment calls to the implementer. Implemented in
`scripts/20260806_pii_cleanup_phase1.sql` (executed) + `exclude_columns` in the
target configs, so the columns cannot re-land:

- **R-1 done (partial by design):** `tb_user_info` dropped `id`, `nickname`,
  `sub_nickname`, `introduce`. `invite_code` deliberately **kept** — referral
  linkage feeds the invite missions; `profile_file_no` kept (inert pointer).
- **R-2 done:** `push_token` dropped (236k values). `title`/`contents` kept —
  still flagged for review (template text).
- **R-3 done (narrowed by measurement):** `call_ctn`/`rcv_ctn` dropped from both
  `*_intr_hist` tables. `sender`/`receiver`/`send_msg` **kept**: each has exactly
  one distinct value — service constants, not personal data.
- **R-4 done:** `target_calorie.user_name`, `user_profiles_log.user_name`,
  `user_master.user_nm`/`birthday`/`birthtime` dropped. Frozen legacy payloads
  stripped in place (durable — nothing writes them since 2026-03-06):
  `user_irs_log.irs_data - 'USERNAME'` (467 rows), `user_profiles_log`
  `irs_data - 'USERNAME'` (476) and `health_profile - 'user_name'` (476).
  `user_master`'s static `age`/`bio_age`/`weight`/`height`/`born_in` remain
  landed (quasi, not in the discard class) and are never selected by staging.
- **R-5 done at column level:** ichms dropped `login_pw`, `login_id`,
  `user_tel` (×2), `login_ip`, `token_id`, `user_name`, `user_birth`,
  `family_name`, `msg_cn`, `chart_no`, `profile_img_url`. **Still open:**
  whether the ichms `auth_*`/`mem_*` tables belong in the warehouse at all.
- **R-6 partially closed:** `stg_irs.irs_data`/`irs_data_log.raw_data` audited —
  0 rows carry `USERNAME` (different structure than feared). `job_input_data`
  genomic retention still open.
- **Live payload keys — settled (owner ruling 2026-08-06):** the landing
  schemas are a transient copy of the sources; de-identification of payload
  *content* (e.g. the `user_intg_log.intg_anlys` top-level `user_name` key,
  re-landed with every new row) happens at the **transform stage** — the D-26
  allow-list is the mechanism, and such keys are never extracted into staging
  or marts. No upstream change is requested.
- **Still open:** R-7 (discovery clinical payload tables), R-8 (re-run on
  target changes).

The classification tables below record the estate **as enumerated on
2026-08-06, before this cleanup** — columns named in the resolution above no
longer exist in the warehouse.

**Standing structural risk:** the loader auto-adds new upstream columns
(`ALTER TABLE … ADD COLUMN`). A new identity column upstream lands in the warehouse with no
signal. This inventory is therefore a snapshot; re-run the enumeration when the extract
targets change, and treat loader "added column" log lines as review triggers. → R-8.

## Recommendations (owner decisions — N-01 says config edits here are policy conversations)

| # | Action | Mechanism |
|---|---|---|
| R-1 | Prune `tb_user_info`: `id`, `nickname`, `sub_nickname`, `introduce`, `invite_code`, `profile_file_no` | `exclude_columns` in `iccoli_targets.py` + retro `DROP COLUMN` script |
| R-2 | Prune `tb_loop_push_history.push_token`; review `title`/`contents` (template text, may embed names) | same |
| R-3 | Prune `call_ctn`, `rcv_ctn`, `sender`, `receiver`, `send_msg` from both `tb_point_item_cpn_*_intr_hist` tables | same |
| R-4 | Prune sibc: `target_calorie.user_name`, `user_profiles_log.user_name` (+ its `age`, `biological_age`), `user_master` `user_nm`/`birthday`/`birthtime`/`age`/`bio_age`/`born_in`; purge or strip the 467 legacy `irs_data` object rows | `exclude_columns` in `sibc_targets.py` (extractor already supports it) + one-off purge SQL like `scripts/20260806_pii_cleanup.sql` |
| R-5 | Decide whether ichms `auth_*`/`mem_*` belong in the warehouse at all (no planned mart uses them). At minimum drop `login_pw`, `user_tel` (×2), `user_name`, `user_birth`, `login_ip`, `token_id`, `chart_no`, `profile_img_url`, `family_name`, `msg_cn`. **`login_pw` should not wait for a phase boundary.** | remove tables from `ichms_targets.py` or `exclude_columns` + retro drop |
| R-6 | Audit `stg_irs.irs_data`/`irs_data_log.raw_data` for the legacy `USERNAME` payload; decide retention of `job_input_data` (genomic inputs, no planned model) | inspection + possible target removal |
| R-7 | Discovery consultation/medical/prescription payload tables feed no planned mart — confirm they are needed or remove from targets | `discovery_targets.py` |
| R-8 | Re-run this enumeration on target-config changes; watch loader added-column logs | process note for the runbook |

---

## Full classification

### stg_iccoli (34 tables, 435 columns) — cohort-filtered at extraction (N-02), N-01 pruning applied

| Table | direct | quasi | sensitive | keys | notes |
|---|---|---|---|---|---|
| tb_action_info | — | — | — | action_no | reference |
| tb_action_mapper | — | — | — | action_no | reference |
| tb_action_user_log | — | — | — | action_log_no, user_no, action_no | `target_data` jsonb keys measured: POINT, TAG_USAGE, ACTIVITY, CONTENT — no identity |
| tb_activity_user_log | — | — | — | action_log_no, user_no, action_no | keyless upstream |
| tb_ext_user_mapper | — | — | — | user_no, ext_user_uuid | the Q-10 translation table |
| tb_loop_push_history | **push_token** (236,008 rows) | — | title, contents (push text; review) | loop_push_id, user_no | **R-2** |
| tb_menu_app | — | — | — | menu_no | admin reference |
| tb_message_send_hist | — | — | — | message_id, user_no | |
| tb_point_item (+_hist, _intr_hist_dtl) | — | — | — | point_item_no etc. | goods/admin catalogue; `no_cpn`-adjacent voucher data is commercial, not personal |
| tb_point_item_cpn | — | — | — | point_item_cpn_no, user_no | `no_cpn` voucher codes are redeemable secrets — access-control, not PII |
| tb_point_item_cpn_issue_intr_hist | **call_ctn, rcv_ctn** (11-digit phone-shaped, 714), sender, receiver | — | send_msg (SMS text) | issue_intr_no, user keys | **R-3** |
| tb_point_item_cpn_state_intr_hist | **call_ctn, rcv_ctn** | — | — | state_intr_no | **R-3** |
| tb_point_item_cpn_cncl_intr_hist | — | — | — | cncl_intr_no | |
| tb_point_item_ctg / _srch_hist_log | — | — | — | ctg/user_no | `srch_keyword` is user-typed text; spot-checked shape only — low risk, keep an eye |
| tb_point_mission (+category, dtl, tag, tag_sub) | — | — | — | mission/category ids | admin reference |
| tb_point_user_dtl / tb_point_user_adj_hist | — | — | — | user_no + ids | point ledger, analytical |
| tb_stats_active_user_cnt / _avg_login_cnt_log / _menu_visit_log | — | — | — | user_no where present | aggregates/visits |
| tb_user_activity_info | — | used_invite_code (referral linkage) | — | user_no | counters analytical |
| tb_user_attendance | — | — | — | user_no | |
| tb_user_device_info | — | model_name, os_type, os_version, app_version (weak fingerprint) | — | user_no | tokens/device ids already pruned (N-01) |
| tb_user_info | **id** (login id), **nickname**, **sub_nickname** | invite_code | introduce (free text) | user_no | **R-1**; dbt staging never selects these |
| tb_user_login_log | — | — | — | user_no | keyless upstream |
| tb_user_personal_info | — | **birth** (full DOB, 'YYMMDD' — reduced to birth_year in dbt staging, D-23), gender, gender_code, nation | — | user_no | ci/di/name/phone/email/telecom already pruned (N-01) |

### stg_sibc (36 tables, 406 columns) — cohort-native, no row filter needed

| Table | direct | quasi | sensitive | keys | notes |
|---|---|---|---|---|---|
| api_logs | — | — | request_body, path_parameter (unaudited request payloads) | id, user_id | may embed anything callers sent |
| chat_msgs | — | — | **content_txt, content_json** (free-text health chat) | msg_id, thread_id | never near marts |
| chat_thread_evts | — | — | payload | evt_id, thread_id | chat event payloads |
| chat_threads | — | — | summary, transcript_cache | thread_id, user_id | chat content in cache columns |
| chat_threads_batch_state | — | — | last_sync_error | thread_id, user_id | operational |
| chat_threads_turns | — | — | submitted_answer, question_snapshot, response | thread_id, event_id | chat content |
| daily_routine_activities / daily_routines | — | — | — | ids, user_id | structured coaching activity — analytical health data |
| disease_factor / disease_info / genetic_trait_info / lifestyle_mapping / signature_type_mapping / onboarding_qstn_master | — | — | — | code keys | reference tables |
| health_assistant_msg | — | — | assistant_message, assistant_summary (per-user health narrative) | user_id | |
| insight_texts / insight_texts_history | — | — | text_for_* (per-user health narrative) | user_id | |
| llm_usage | — | — | error_message, raw_usage, meta (may echo prompt fragments) | id, user_id, session_id | mostly operational |
| send_messages | — | — | transmit_title, transmit_msg | msg_id, user_id | outbound message content |
| target_calorie | **user_name** (404 rows) | — | health_status_summary, dietary_precautions, nutrition_precautions, general_dietary_recommendations | id, user_id | **R-4** |
| user_bhv_log | — | — | bhv_anlys (unaudited jsonb) | user_id | |
| user_checkup_log | — | — | **checkup_data, checkup_anlys** (clinical checkup results) | user_id | |
| user_diet_analysis | — | — | meal_data, ai_analysis, next_meal_tips | user_id | |
| user_dtc_log | — | — | **dtc_data, dtc_anlys** (genomic) | user_id | special category |
| user_event_log | — | — | — | seq, user_id | |
| user_guardrail | — | — | **patient_summary, clinician_approved_text, lifestyle_guide*** (clinical) | user_id | |
| user_intg_log | — | — | intg_anlys (contains top-level `user_name` key — drift-guarded, never extracted; D-26) | user_id | staging extracts allow-listed keys only |
| user_irs_log | — | — | **irs_data** (467 legacy object rows with `USERNAME`, `1_AGE`, `WEIGHT` keys), irs_anlys | user_id | **R-4**; staging never selects irs_data |
| user_master | **user_nm** | **birthday, birthtime** (full DOB+time), age, bio_age, weight, height, born_in, sex | — | user_id | **R-4**; dbt staging selects only user_id, sex, joined_dt, timezone |
| user_profiles_log | **user_name** (476 rows) | age, biological_age | irs_data, dtc_data, rag_data, health_profile, irs_analyze, dtc_analyze, behavior_analyze, profile_analyze (large unaudited jsonb incl. genomics) | user_id | **R-4** |
| user_routine_fdbk | — | — | fdbk (free-ish text) | fdbk_id, user_id, thread_id | low |
| user_signature_type | — | — | — | user_id | analytical typing |
| user_state_log | — | — | snapshot_json (unaudited) | user_id | |
| user_unavl_periods | — | — | note (free text) | user_id | low |
| weekly_routine_goal / weekly_routine_plan | — | — | — | ids, user_id | structured coaching |

### stg_ichms (16 tables, 138 columns) — **not cohort-filtered; ~16k accounts** — R-5

| Table | direct | quasi | sensitive | keys | notes |
|---|---|---|---|---|---|
| auth_client / auth_customer | — | — | — | client_id, customer_id | customer_name is an org name |
| auth_user | **user_tel** (575/578 rows) | — | — | user_id | |
| auth_user_account | **login_id, login_pw** (16,184 bcrypt hashes) | — | — | user_account_id, user_id | **credential material — most urgent item in this document** |
| auth_user_customer | — | — | — | ids | |
| auth_user_login_history | **login_ip**, token_id (session-token identifier) | — | — | user_id | |
| auth_user_profile | **user_name** | **user_birth**, gender_se_cd | — | user_id | |
| auth_user_withdraw_history | **user_tel** | — | — | user_id | |
| cnet_event_info_transmit_history | — | — | transmit_data (unaudited) | receiver_user_id | |
| cnet_push_info_transmit_history | — | — | transmit_title, transmit_msg, link_url | receiver_user_id | |
| com_code / com_code_language_map | — | — | — | com_cd | reference |
| cudc_workflow_history | — | — | input_data (unaudited) | transaction_id | |
| mem_family | **family_name** | family_user_id + family_relation_se_cd (family-network linkage) | — | family_sn, user_id | |
| mem_family_msg | — | — | **msg_cn** (free-text family messages) | family_msg_sn, family_sn | |
| mem_user | **chart_no** (medical record number), **profile_img_url** | — | — | user_id | |

### stg_irs (5 tables, 47 columns)

| Table | direct | quasi | sensitive | keys | notes |
|---|---|---|---|---|---|
| disease_info | — | — | — | disease_id | reference |
| irs_data | — | — | raw_data (unaudited; upstream of the legacy payload that carries `USERNAME`) | user_id | **R-6** |
| irs_data_log | — | — | raw_data (same) | seq, user_id | **R-6** |
| job_input_data | — | — | **genotype** (5,787 rows — genomic), medical, profile, lifestyle, merged_data, result_data | job_id, user_id | **R-6**; no planned mart reads it |
| user_irs_hist | — | — | — | user_id, disease_id | the scalar score table; fully analytical — this is what dbt staging models |

### stg_discovery (32 tables, 220 columns)

| Table | direct | quasi | sensitive | keys | notes |
|---|---|---|---|---|---|
| disc_consultation_user_info | — | — | **consultation_data** (medical consultation) | *_sn keys | **R-7** |
| disc_disease_detail_info | — | — | — | *_sn | reference |
| disc_dtc_user_info | — | — | **user_dtc_data** (genomic) | *_sn | special category |
| disc_examination_user_info | — | — | **examination_data** (clinical) | *_sn | **R-7** |
| disc_genomic_user_info | receipt_no (lab receipt identifier) | — | genomic linkage record | user_genomic_sn, user_id | |
| disc_globalization_code | — | — | — | global_cd | empty at source (0 rows) |
| disc_health_info_meta / _detail | — | — | — | *_sn | reference |
| disc_health_user_info | — | — | health_info_data (unaudited health jsonb) | *_sn, user_id | |
| disc_irs_user_info | — | — | user_irs_data (unaudited) | *_sn | |
| disc_lifelog_* (12 tables: activity, bloodglucose, bloodpressure, body_info, bodyfat, food, grip_strength, heartrate, meal, oxygen_saturation, sleep, sleep_detail) | — | — | — | user_lifelog_sn / user_sleep_sn | structured measurements — analytical; feeds fct_measurement (Phase 3) |
| disc_lifestyle_survey_question_detail / _option | — | — | — | *_sn | reference |
| disc_lifestyle_user_survey_answer | — | — | user_answer_data (survey answers; `is_etc` options allow free text) | *_sn, user_id | |
| disc_medical_user_info | — | — | **medical_data** | *_sn | **R-7** |
| disc_prescription_medicine_user_info | — | — | **prescription_medicine_data** | *_sn | **R-7** |
| disc_race_info_meta_info | — | race_se_cd | — | — | special-category quasi |
| disc_survey_discovery_version | — | — | — | *_sn | reference |
| disc_user_disease_answer / disc_user_disease_history | — | — | disease history answers | *_sn, user_id | |
| disc_user_race_info_history | — | **race_se_cd** | — | *_sn, user_id | special-category quasi |
