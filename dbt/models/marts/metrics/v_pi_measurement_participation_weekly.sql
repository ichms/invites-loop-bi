-- PI: 측정 참여도 (주별) — distinct users submitting at least one device
-- measurement per week.
--
-- Weekly, not daily: device measurement is intermittent by nature (a blood
-- pressure cuff is not a daily obligation), and a daily series is mostly noise
-- around zero. Weeks start Monday, matching MB_START_OF_WEEK (D-18).

select
	date_trunc('week', measured_date)::date as week_start_date,
	count(distinct user_id) as measuring_users,
	count(*) as readings
from {{ ref('fct_measurement') }}
group by 1
