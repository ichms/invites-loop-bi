-- Grain: one row per user_id.
--
-- The source is already pruned at extraction (N-01): ci/di/name/phone/email/
-- telecom never land. What remains is reduced here: birth ('YYMMDD', two-digit
-- year) becomes birth_year (D-23) and the raw value is never selected past
-- that expression.

with loop_users as (

	-- Q-10 translation, filtered inside the CTE — a left join below plus an
	-- outer WHERE would silently turn into an inner join and drop unmapped
	-- rows without a signal. The not_null test on user_id is the signal.
	select
		user_no,
		ext_user_uuid as user_id
	from {{ source('stg_iccoli', 'tb_ext_user_mapper') }}
	where ext_system_code = 'LOOP'

),

source as (

	select
		user_no,
		birth,
		gender,
		gender_code,
		nation,
		verify_datetime,
		create_datetime,
		update_datetime
	from {{ source('stg_iccoli', 'tb_user_personal_info') }}

)

select
	u.user_id,
	-- Century pivot for the two-digit year: values above the current two-digit
	-- year are 19xx ('52' → 1952 for a 74-year-old; '10' → 2010). Correct for
	-- any birth year in (today − 99, today], which covers an adult cohort.
	case
		when s.birth ~ '^\d{6}$' then
			case
				when substring(s.birth, 1, 2)::int <= extract(year from current_date)::int % 100
					then 2000 + substring(s.birth, 1, 2)::int
				else 1900 + substring(s.birth, 1, 2)::int
			end
	end as birth_year,
	s.gender,
	s.gender_code,
	s.nation,
	s.verify_datetime,
	s.create_datetime,
	s.update_datetime
from source as s
left join loop_users as u using (user_no)
