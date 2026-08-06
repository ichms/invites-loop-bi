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
--   weight, height               point-in-time snapshot that silently rots;
--                                measurements belong to fct_measurement
--   intg_anlys,
--   discovery_collection_status  operational JSONB, not modelled

select
	user_id,
	sex,
	joined_dt,
	timezone,
	created_at,
	updated_at
from {{ source('stg_sibc', 'user_master') }}
