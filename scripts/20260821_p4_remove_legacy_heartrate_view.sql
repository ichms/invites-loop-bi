begin;

-- The dbt model now resolves to the canonical physical relation in
-- intermediate_private. Keeping this orphaned view would leave a second path
-- that regroups the entire landing heart-rate table on every direct query.
drop view if exists staging.stg_discovery__lifelog_wearable_heartrate restrict;

commit;
