-- PI: 코칭 순응도 (일별) — share of delivered JITAI activities that were completed.
--
-- Denominator is EVERY delivered activity, including withdrawn ones: an
-- activity the system pulled back is still an intervention that did not land.
-- Filtering those out would quietly inflate the rate.

select
	ymd_date,
	count(*) as activities_delivered,
	count(*) filter (where is_completed) as activities_completed,
	round(100.0 * count(*) filter (where is_completed) / nullif(count(*), 0), 1) as adherence_pct
from {{ ref('fct_coaching_event') }}
group by 1
