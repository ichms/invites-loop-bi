-- Grain: one row per device_type_code.
--
-- Labels come from the ichms `com_code` table (parent code 20301300), which is
-- where the Discovery platform keeps its enumerations. Korean names are the
-- authoritative ones — the Planning Team slices on them (D-10 rationale) — and
-- the English column is a hand-written convenience, not a source field.
--
-- This dim is what makes the density difference sliceable rather than a
-- footnote: a blood-pressure cuff and a smartwatch produce very different row
-- volumes, and a chart that does not separate them is misleading.

select
	com_cd as device_type_code,
	cd_nm as device_type_name_kor,
	case com_cd
		when '20301301' then 'Blood pressure monitor'
		when '20301302' then 'Grip dynamometer'
		when '20301303' then 'InBody (height/weight)'
		when '20301304' then 'InBody (body composition)'
		when '20301305' then 'Kiosk (manual entry)'
		when '20301306' then 'Smartwatch'
		when '20301307' then 'Meal'
		when '20301308' then 'Invites Loop (manual entry)'
	end as device_type_name_eng
from {{ source('stg_ichms', 'com_code') }}
where up_cd = '20301300'
