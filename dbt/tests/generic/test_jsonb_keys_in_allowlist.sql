{#
  D-27 schema-drift test. Fails — naming the key — when a payload column contains
  a top-level JSONB key the allow-list seed does not know. Pass the seed's
  source_table value as allowlist_table (the tested relation's own name cannot be
  used, because the test also runs against source() relations).

  Allow-listing alone makes drift invisible; this test is the visibility half of
  the D-26/D-27 pair. On failure: classify the new key, add it to
  seeds/jsonb_allowlist.csv (extract=false by default), re-run.
#}
{% test jsonb_keys_in_allowlist(model, column_name, allowlist_table) %}

select
	k as unexpected_jsonb_key,
	count(*) as row_count
from {{ model }} as src,
	lateral jsonb_object_keys(src.{{ column_name }}) as k
where jsonb_typeof(src.{{ column_name }}) = 'object'
	and k not in (
		select jsonb_key
		from {{ ref('jsonb_allowlist') }}
		where source_table = '{{ allowlist_table }}'
			and payload_column = '{{ column_name }}'
	)
group by 1

{% endtest %}
