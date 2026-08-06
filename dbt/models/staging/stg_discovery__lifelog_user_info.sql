-- Grain: one row per user_lifelog_sn (the lifelog transaction).
--
-- This is the ONLY place a lifelog measurement gains a user_id: every
-- per-measurement table (bloodpressure, body_info, bodyfat, …) keys on
-- user_lifelog_sn and carries no user key of its own. Every measurement model
-- joins through here.
--
-- The device/platform columns are com_code values (ichms `com_code`), resolved
-- to labels in dim_device_type rather than here, so the codes stay joinable.

select
	user_lifelog_sn,
	user_id,
	measure_platform as measure_platform_code,
	measure_device_type as device_type_code,
	measure_location,
	measured_user_timezone,
	ins_dt as recorded_at
from {{ source('stg_discovery', 'disc_lifelog_user_info') }}
where user_id is not null
