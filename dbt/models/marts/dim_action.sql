-- Grain: one row per action_no. The app-action catalogue behind fct_app_action
-- (Phase 3); built now because dim_action is what turns an opaque action_no in
-- the fact into something a Planning Team member can filter on.

select
	action_no,
	action_category,
	action_type,
	description,
	create_datetime as created_at
from {{ ref('stg_iccoli__tb_action_info') }}
