{#
  D-05 null-rate threshold test, the partner of not_null for fields extracted
  from a moving JSONB contract: a key rename upstream does not error, it
  produces NULLs and flatlines the dashboard. Thresholds are set per column in
  staging.yml against the null rate measured on 2026-08-06, with slack for
  ordinary noise — a breach means the extraction path is broken, not that the
  data got slightly worse.
#}
{% test null_rate_below(model, column_name, max_null_rate) %}

select
	null_rate,
	{{ max_null_rate }} as max_allowed
from (
	select
		count(*) filter (where {{ column_name }} is null)::numeric
			/ nullif(count(*), 0) as null_rate
	from {{ model }}
) as rates
where null_rate > {{ max_null_rate }}

{% endtest %}
