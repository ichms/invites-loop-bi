-- GRAIN: one row per current cohort user and current approved deployment site.
--
-- This is deliberately a current-state bridge, not a temporal fact. iCHMS
-- overwrites customer_id in place and does not preserve the previous site or
-- the actual switch timestamp. Joining this relation to historical events can
-- answer "where is this user assigned now?" only; it cannot answer where an
-- event happened.

select
	u.user_id,
	s.site_id as current_site_id
from {{ ref('dim_user') }} as u
inner join {{ ref('stg_ichms__current_user_deployment_site') }} as s using (user_id)
inner join {{ ref('dim_deployment_site') }} as d
	on d.site_id = s.site_id
