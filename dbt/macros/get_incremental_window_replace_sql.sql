{% macro get_incremental_window_replace_sql(arg_dict) %}

	{%- set target_relation = arg_dict['target_relation'] -%}
	{%- set temp_relation = arg_dict['temp_relation'] -%}
	{%- set dest_columns = arg_dict['dest_columns'] -%}
	{%- set window_column_name = config.get('window_column') -%}
	{%- set window_lookback_days = config.get('window_lookback_days') -%}

	{% if not window_column_name or not window_lookback_days %}
		{{ exceptions.raise_compiler_error(
			"incremental_strategy='window_replace' requires window_column and window_lookback_days"
		) }}
	{% endif %}

	{%- set window_column = adapter.quote(window_column_name) -%}
	{%- set dest_cols_csv = get_quoted_csv(dest_columns | map(attribute='name')) -%}

	-- The model SQL is materialized into the temporary relation before this
	-- statement runs. Calculate the target cutoff before deleting, then replace
	-- the whole configured event-time window, including payloads that disappeared
	-- upstream. The temp minimum is only the empty-target bootstrap fallback.
	delete from {{ target_relation }}
	where {{ window_column }} >= (
		select coalesce(
			max({{ window_column }})
				- ({{ window_lookback_days }} * interval '1 day'),
			(select min({{ window_column }}) from {{ temp_relation }})
		)
		from {{ target_relation }}
	);

	insert into {{ target_relation }} ({{ dest_cols_csv }})
	select {{ dest_cols_csv }}
	from {{ temp_relation }}

{% endmacro %}
