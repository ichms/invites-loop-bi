-- GRAIN: one row per (user_id, ymd_date) — identical to fct_user_day.
--
-- Convenience layer over the time-aware behavioural panel. Current site stays
-- out because it cannot be used for historical/as-of attribution; use
-- bridge_user_site_current only for a clearly labelled current filter.
--
-- Deliberately omitted from the dim join:
--   site_id     current-state SCD1 only; unsafe for historical/as-of attribution
--   weight_kg / height_cm / bmi   raw anthropometrics stay on dim_user for
--                                controlled analysis; aggregate reporting gets
--                                bmi_band only, like age_band_5y

select
	f.*,

	u.sex,
	u.birth_year,
	u.joined_dt,
	u.is_mapped,
	u.bmi_band,
	u.cohort_group,

	d.year_number,
	d.year_month,
	d.week_start_date,
	d.is_weekend
from {{ ref('fct_user_day') }} as f
left join {{ ref('dim_user') }} as u using (user_id)
left join {{ ref('dim_date') }} as d
	on d.date_day = f.ymd_date
