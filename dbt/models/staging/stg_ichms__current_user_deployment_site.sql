-- Grain: one row per user_id under the current iCHMS write contract.
-- This is current-state attribution only: an in-place customer_id update moves
-- the user and does not preserve the previous site or the actual switch time.
-- The grain test fails if the source ever exposes two active approved sites.

select
	user_id,
	customer_id as site_id,
	user_customer_id,
	linked_dt
from {{ source('stg_ichms', 'auth_user_customer') }}
where customer_id in (
	'2e0a3387-7058-4f9e-a134-2017f7b7000b'::uuid, -- Ulsan
	'778d4ff7-ab76-4070-a9a9-716fac93d9c9'::uuid  -- Jeju
)
	and unlinked_dt is null
