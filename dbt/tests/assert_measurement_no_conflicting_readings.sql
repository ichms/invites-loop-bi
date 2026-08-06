-- fct_measurement collapses the same reading arriving under several lifelog
-- transaction ids (device re-sync). That is safe only while the collapsed rows
-- AGREE: 36 such groups exist today and all 36 carry one distinct value.
--
-- If two different values ever land in the same (user, timestamp, metric) slot,
-- the fact's `distinct on` picks one by transaction id — an arbitrary choice
-- that would put an unexplainable number in front of the Planning Team. That is
-- a decision for a human, so this fails the build rather than warning: which
-- reading is right depends on why they disagree.

select
	l.user_id,
	m.measured_at,
	m.metric_code,
	count(distinct m.metric_value) as distinct_values
from {{ ref('stg_discovery__lifelog_measurements') }} as m
inner join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
group by 1, 2, 3
having count(distinct m.metric_value) > 1
