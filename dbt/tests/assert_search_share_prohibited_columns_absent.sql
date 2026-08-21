-- Defense in depth: the P0 fields and raw source actor serials may exist in the
-- restricted landing layer, but none may appear in the new dbt staging or
-- general-mart relations.

with model_dependencies as (

	select count(*) as row_count from {{ ref('stg_iccoli__tb_search_log') }}
	union all
	select count(*) from {{ ref('stg_iccoli__tb_share_info') }}
	union all
	select count(*) from {{ ref('stg_iccoli__tb_share_log') }}
	union all
	select count(*) from {{ ref('fct_app_search_event') }}
	union all
	select count(*) from {{ ref('fct_share_link') }}
	union all
	select count(*) from {{ ref('fct_share_interaction_event') }}

),

prohibited_columns as (

	select
		table_schema,
		table_name,
		column_name
	from information_schema.columns
	where table_schema in ('staging', 'marts')
		and table_name in (
			'stg_iccoli__tb_search_log',
			'stg_iccoli__tb_share_info',
			'stg_iccoli__tb_share_log',
			'fct_app_search_event',
			'fct_share_link',
			'fct_share_interaction_event'
		)
		and column_name in (
			'word',
			'share_key',
			'to_user_ip',
			'to_user_agent',
			'to_user_no',
			'target_no',
			'user_no',
			'from_user_no'
		)

)

select *
from prohibited_columns
where (select count(*) from model_dependencies) >= 0
