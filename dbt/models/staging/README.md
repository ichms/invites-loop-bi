# staging — dbt staging models (views in the `staging` schema)

**Do not confuse this with the `stg_<system>` schemas.** Those are the EL
landing layer, written by the Airflow extract/load DAGs and declared here as
dbt *sources*. Models in this directory read from them and materialise as
views in the warehouse schema `staging`.

File naming: `stg_<system>__<table>.sql` (dbt convention).

What belongs here (and nowhere downstream):

- Q-01 dedupe: `user_intg_log` / `user_irs_log` keep the last row per
  `(user_id, ymd)` by `created_at`.
- Casts: `ymd` (varchar in the source) → `date`.
- Key translation: `user_no` → `user_id` through `tb_ext_user_mapper`,
  filtered to `ext_system_code = 'LOOP'` **inside the CTE** — no mart model
  ever sees a `user_no`.
- JSONB flattening through the allow-list seed (D-26); the drift test (D-27)
  fails the build when the payload grows a key the allow-list does not know.
- PII reduction (D-22/D-23): `birth` → `birth_year int`; no username column
  is ever selected.

**One model here is a table, not a view.** `stg_discovery__lifelog_wearable_day`
is `materialized='table'` because `disc_lifelog_user_heartrate` alone is ~8.5M
sample rows; as a view it would re-scan on every downstream query and every
Superset chart. It collapses to a few thousand user-days, so the table is small
even though its input is not. Keep the exception rare and justified in the
model header.

**Lifelog models gain their user through a join.** Every per-measurement
discovery table keys on `user_lifelog_sn` and carries no user of its own —
`stg_discovery__lifelog_user_info` is the only place a `user_id` appears. A CTE
that selects `user_id` straight from a measurement or meal source will not
compile.
