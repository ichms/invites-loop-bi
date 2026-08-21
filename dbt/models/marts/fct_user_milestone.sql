-- GRAIN: one user × observed milestone code (first real occurrence only).
--
-- joined_dt is a source DATE, so cohort_enrolled carries occurred_date with a
-- null occurred_at and DATE temporal_precision. Every other milestone uses a
-- real source timestamp. No timestamp is fabricated and no missing funnel
-- stage is emitted as a placeholder.

with candidates as (

	select
		user_id,
		'cohort_enrolled'::text as milestone_code,
		joined_dt::date as occurred_date,
		null::timestamptz as occurred_at,
		'DATE'::text as temporal_precision,
		'stg_sibc__user_master'::text as source_relation
	from {{ ref('dim_user') }}

	union all

	select user_id, 'iccoli_mapped', (mapped_at at time zone 'Asia/Seoul')::date, mapped_at, 'TIMESTAMP', 'stg_iccoli__tb_ext_user_mapper'
	from {{ ref('stg_iccoli__tb_ext_user_mapper') }}

	union all

	select user_id, 'first_app_login', login_date, logged_in_at, 'TIMESTAMP', 'fct_app_login_event'
	from {{ ref('fct_app_login_event') }}

	union all

	select user_id, 'first_app_action', action_date, action_datetime, 'TIMESTAMP', 'fct_app_action'
	from {{ ref('fct_app_action') }}

	union all

	select user_id, 'first_app_search', search_date, searched_at, 'TIMESTAMP', 'fct_app_search_event'
	from {{ ref('fct_app_search_event') }}

	union all

	select user_id, 'first_share_created', share_created_date, share_created_at, 'TIMESTAMP', 'fct_share_link'
	from {{ ref('fct_share_link') }}

	union all

	select user_id, 'first_share_interaction', interaction_date, interaction_at, 'TIMESTAMP', 'fct_share_interaction_event'
	from {{ ref('fct_share_interaction_event') }}

	union all

	select user_id, 'first_coaching_delivered', ymd_date, delivered_at, 'TIMESTAMP', 'fct_coaching_event'
	from {{ ref('fct_coaching_event') }}

	union all

	select user_id, 'first_measurement', measured_date, measured_at, 'TIMESTAMP', 'fct_measurement'
	from {{ ref('fct_measurement') }}

),

ranked as (

	select
		*,
		row_number() over (
			partition by user_id, milestone_code
			order by occurred_date, occurred_at nulls first
		) as occurrence_rank
	from candidates
	where user_id is not null
		and occurred_date is not null

)

select
	r.user_id,
	r.milestone_code,
	r.occurred_date,
	r.occurred_at,
	r.temporal_precision,
	r.source_relation
from ranked as r
inner join {{ ref('dim_user') }} as u using (user_id)
where r.occurrence_rank = 1
