{#
  Use a model's +schema config verbatim.

  dbt's default is "<profile schema>_<custom schema>", which would produce
  staging_staging / staging_marts. The layout here is fixed and documented in
  dbt_project.yml (staging / marts), so the custom name is taken as-is.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
	{%- if custom_schema_name is none -%}
		{{ target.schema }}
	{%- else -%}
		{{ custom_schema_name | trim }}
	{%- endif -%}
{%- endmacro %}
