-- PI: 앱 참여도 (일별) — distinct cohort users performing any app action per day.
--
-- Counts USERS, not actions: an action count moves when one enthusiast taps
-- more, which is not engagement improving.

select
	action_date,
	count(distinct user_id) as active_users,
	count(*) as actions
from {{ ref('fct_app_action') }}
group by 1
