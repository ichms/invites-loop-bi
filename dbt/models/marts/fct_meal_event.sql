-- GRAIN: one meal record per source lifelog transaction and recorded timestamp.
-- meal_data/image references never enter this fact. source_transaction_id is
-- retained because the keyless meal source needs its parent transaction to
-- state and reconcile the grain honestly.

select
	md5(concat_ws('|', m.user_lifelog_sn::text, m.recorded_at::text)) as meal_event_id,
	m.user_id,
	m.user_lifelog_sn as source_transaction_id,
	m.recorded_at,
	m.recorded_date
from {{ ref('stg_discovery__lifelog_meal') }} as m
inner join {{ ref('dim_user') }} as u using (user_id)
