-- Every lifelog measurement must resolve to a user through the lifelog parent
-- transaction. fct_measurement inner-joins that parent, so an unresolvable
-- reading would silently vanish from the fact rather than fail — exactly the
-- quiet undercount the loud-failure rule exists to prevent.
--
-- Background: the parent table (disc_lifelog_user_info) was not an extraction
-- target until 2026-08-06, so this used to be 100% unattributable. If the
-- parent's ELT ever falls behind its children, this fires.

select
	m.user_lifelog_sn,
	count(*) as unattributed_readings
from {{ ref('stg_discovery__lifelog_measurements') }} as m
left join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
where l.user_lifelog_sn is null
group by 1
