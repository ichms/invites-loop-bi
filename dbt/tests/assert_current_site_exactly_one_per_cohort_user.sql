-- Every current cohort user must have exactly one approved current site. This
-- does not create site history; it only pins the current source contract.

select
	u.user_id,
	count(b.current_site_id) as current_site_count
from {{ ref('dim_user') }} as u
left join {{ ref('bridge_user_site_current') }} as b using (user_id)
group by 1
having count(b.current_site_id) <> 1
