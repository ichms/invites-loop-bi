-- Grain: one row per owner-approved deployment site.
-- auth_customer also contains application tenants; only these two customer IDs
-- are deployment sites for reporting (owner rule, 2026-08-13).

select
	customer_id as site_id,
	customer_name as site_name_kor,
	customer_name_en as site_name_eng,
	is_active,
	created_dt,
	updated_dt
from {{ source('stg_ichms', 'auth_customer') }}
where customer_id in (
	'2e0a3387-7058-4f9e-a134-2017f7b7000b'::uuid, -- Ulsan
	'778d4ff7-ab76-4070-a9a9-716fac93d9c9'::uuid  -- Jeju
)
	and not is_deleted
