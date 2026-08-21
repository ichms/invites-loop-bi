-- GRAIN: one row per share_no for an actor in the current SiBC cohort.
--
-- A row is link/object creation. It is not an interaction count. The source
-- share key and polymorphic target_no never enter this general mart.

with links as (

	select
		share_no,
		user_id,
		share_type,
		share_created_at,
		share_created_date
	from {{ ref('stg_iccoli__tb_share_info') }}

),

cohort as (

	select user_id
	from {{ ref('dim_user') }}

)

select l.*
from links as l
inner join cohort as c using (user_id)
