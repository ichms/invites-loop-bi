-- N-02/P1: mapper entries without a current sibc.user_master row are a dynamic
-- reconciliation population, not a pinned production count. They may remain
-- visible in staging but must not leak into current-cohort facts.

with mapper_only as (

	select x.user_id
	from {{ ref('stg_iccoli__tb_ext_user_mapper') }} as x
	left join {{ ref('stg_sibc__user_master') }} as m using (user_id)
	where m.user_id is null

),

fact_users as (

	select 'search'::text as channel, search_log_no::text as event_id, user_id
	from {{ ref('fct_app_search_event') }}

	union all

	select 'share_link', share_no::text, user_id
	from {{ ref('fct_share_link') }}

	union all

	select 'share_interaction', share_log_no::text, user_id
	from {{ ref('fct_share_interaction_event') }}

)

select
	f.channel,
	f.event_id,
	f.user_id
from fact_users as f
inner join mapper_only as m using (user_id)
