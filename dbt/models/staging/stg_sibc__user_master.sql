-- Grain: one row per user_id. This is the cohort population (N-02) — dim_user
-- builds from here, not from the mapper.
--
-- user_nm, birthday and birthtime no longer land at all (dropped + excluded at
-- extraction 2026-08-06, PII_INVENTORY.md R-4). Still landed but never
-- selected, deliberately (D-22/D-23/D-24):
--   age, bio_age                 static age columns rot in an SCD1 world —
--                                age is computed at activity time in the facts
--                                (birth_year comes from
--                                stg_iccoli__tb_user_personal_info)
--   born_in                      birthplace; quasi-identifier at n≈400
--   intg_anlys,
--   discovery_collection_status  operational JSONB, not modelled
--
-- weight / height ARE selected (Frame 2 / todo.md item B, 2026-08-13). They are
-- an enrolment-time snapshot for segment moderation (bmi_band on dim_user), not
-- a longitudinal measurement series — those stay in fct_measurement. Zeros are
-- treated as missing: three cohort rows carry weight=0 and height=0.

select
	user_id,
	sex,
	joined_dt,
	timezone,
	nullif(weight, 0) as weight_kg,
	nullif(height, 0) as height_cm,
	created_at,
	updated_at
from {{ source('stg_sibc', 'user_master') }}
