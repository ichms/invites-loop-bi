-- Grain: one row per user_id (mapper is strict 1:1, verified 2026-08-06 and
-- enforced with a unique test).
--
-- The Q-10 election means user_no never leaves staging: this model exposes the
-- cohort-native uuid only. The other stg_iccoli__* models do their own
-- translation join inside their CTE (join hygiene per the decision log) rather
-- than ref()-ing this model, so this one exists for dim_user's is_mapped flag
-- and the orphan-count tests.

select
	ext_user_uuid as user_id,
	create_datetime as mapped_at
from {{ source('stg_iccoli', 'tb_ext_user_mapper') }}
-- The mapper is designed to fan out to other external systems later; every
-- consumer must filter to the Loop cohort.
where ext_system_code = 'LOOP'
