-- An observed zero/activity may carry a number. Every other state must carry
-- NULL, preventing stale, ineligible, or unknown periods from becoming zeros.

select user_id, ymd_date, 'app_login' as channel from {{ ref('fct_user_day') }}
where (app_login_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO')) <> (app_login_events is not null)
union all
select user_id, ymd_date, 'app_action' from {{ ref('fct_user_day') }}
where (app_action_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO')) <> (app_actions is not null)
union all
select user_id, ymd_date, 'app_search' from {{ ref('fct_user_day') }}
where (app_search_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO')) <> (app_search_events is not null)
union all
select user_id, ymd_date, 'share_created' from {{ ref('fct_user_day') }}
where (share_created_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO')) <> (share_links_created is not null)
union all
select user_id, ymd_date, 'share_interaction' from {{ ref('fct_user_day') }}
where (share_interaction_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO')) <> (share_interaction_events is not null)
union all
select user_id, ymd_date, 'coaching' from {{ ref('fct_user_day') }}
where (coaching_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO')) <> (routines_delivered is not null)
union all
select user_id, ymd_date, 'measurement' from {{ ref('fct_user_day') }}
where (measurement_state = 'OBSERVED_ACTIVITY') <> (manual_measurements is not null)
union all
select user_id, ymd_date, 'meal' from {{ ref('fct_user_day') }}
where (meal_state = 'OBSERVED_ACTIVITY') <> (meal_records is not null)
union all
select user_id, ymd_date, 'wearable' from {{ ref('fct_user_day') }}
where (wearable_state = 'OBSERVED_ACTIVITY') <> (wearable_streams_active is not null)
