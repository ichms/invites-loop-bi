-- Grain: one row per action_no. Reference table behind dim_action; carries no
-- user key, so no translation.

select
	action_no,
	action_category,
	action_type,
	description,
	create_datetime
from {{ source('stg_iccoli', 'tb_action_info') }}
