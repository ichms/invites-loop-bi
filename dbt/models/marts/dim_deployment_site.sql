-- Grain: one row per deployment site.
--
-- Owner-approved site allow-list (2026-08-13): Ulsan and Jeju customer UUIDs
-- only. auth_customer also contains application tenants, so adding another row
-- is an owner decision rather than an inference from that table.

select
	site_id,
	site_name_kor,
	site_name_eng,
	'KR' as country_code
from {{ ref('stg_ichms__deployment_site') }}
