-- PI: 도메인별 코칭 순응도 — the same metric sliced by behaviour domain
-- (diet / exercise / sleep / stress / insight).
--
-- Separate view rather than a column on the daily one: one metric per view
-- (D-10). "Adherence overall" and "adherence by domain" answer different
-- questions and will be cited in different sentences.

select
	domain,
	count(*) as activities_delivered,
	count(*) filter (where is_completed) as activities_completed,
	round(100.0 * count(*) filter (where is_completed) / nullif(count(*), 0), 1) as adherence_pct
from {{ ref('fct_coaching_event') }}
group by 1
