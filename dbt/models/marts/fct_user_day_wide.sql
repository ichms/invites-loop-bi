-- GRAIN: one row per (user_id, ymd_date) — identical to fct_user_day.
--
-- Wide convenience layer over the behavioural panel (HOWTO.md §3 Option A).
-- Superset charts read one dataset; multi-angle filters on sex / bmi_band /
-- cohort_group / observability need those columns on the same relation as the
-- panel measures. The star (fct_user_day + dim_user + dim_date) stays the
-- source of truth; this model is the Planning-Team self-serve surface.
--
-- Deliberately omitted from the dim join:
--   site_id     hardcoded constant — filtering on it is meaningless (see dim_user)
--   weight_kg / height_cm / bmi   raw anthropometrics stay on dim_user for
--                                notebooks; the GUI gets bmi_band only (Q-12
--                                same rationale as age_band_5y vs age_at_activity)

select
	f.*,

	u.sex,
	u.birth_year,
	u.joined_dt,
	u.is_mapped,
	u.bmi_band,
	u.cohort_group,
	u.is_observable_app_login,
	u.is_observable_routine,
	u.is_observable_manual_measurement,
	u.is_observable_meal,
	u.is_observable_wearable,
	u.is_observable_wearable_and_routine,

	d.year_number,
	d.year_month,
	d.week_start_date,
	d.is_weekend
from {{ ref('fct_user_day') }} as f
left join {{ ref('dim_user') }} as u using (user_id)
left join {{ ref('dim_date') }} as d
	on d.date_day = f.ymd_date
