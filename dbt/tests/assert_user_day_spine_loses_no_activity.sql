-- fct_user_day's spine is bounded — it runs from the earlier of enrolment and
-- first activity, up to the observation frontier. Any behavioural row falling
-- outside those bounds is dropped SILENTLY: the fact still builds, every grain
-- and not_null test still passes, and the only symptom is a total that is
-- quietly too small.
--
-- That is not hypothetical. The first version of this spine started at
-- joined_dt, which dropped 381 meal records and removed 23 of 335 meal
-- recorders entirely, because their records predated study enrolment. Nothing
-- failed. It was found by reconciling against the source.
--
-- So the invariant is asserted directly: for each channel, what the fact totals
-- must equal what staging holds for cohort users. This is the test that makes
-- the spine bounds safe to change.

with cohort as (

    select user_id from {{ ref('dim_user') }}

),

expected as (

    select
        'meal_records' as channel,
        count(*) as expected_total
    from {{ ref('stg_discovery__lifelog_meal') }}
    inner join cohort using (user_id)

    union all

    select
        'manual_measurements',
        count(*)
    from {{ ref('stg_discovery__lifelog_measurements') }} as ms
    inner join {{ ref('stg_discovery__lifelog_user_info') }} as li
        using (user_lifelog_sn)
    inner join cohort as c on c.user_id = li.user_id

    union all

    select
        'app_login_events',
        count(*)
    from {{ ref('stg_iccoli__tb_user_login_log') }}
    inner join cohort using (user_id)

    union all

    select
        'app_actions',
        count(*)
    from {{ ref('stg_iccoli__tb_action_user_log') }}
    inner join cohort using (user_id)

),

actual as (

    select 'meal_records' as channel, sum(meal_records) as actual_total from {{ ref('fct_user_day') }}
    union all select 'manual_measurements', sum(manual_measurements) from {{ ref('fct_user_day') }}
    union all select 'app_login_events', sum(app_login_events) from {{ ref('fct_user_day') }}
    union all select 'app_actions', sum(app_actions) from {{ ref('fct_user_day') }}

)

select
    e.channel,
    e.expected_total,
    a.actual_total,
    e.expected_total - a.actual_total as rows_lost_outside_spine
from expected as e
inner join actual as a using (channel)
where e.expected_total is distinct from a.actual_total
