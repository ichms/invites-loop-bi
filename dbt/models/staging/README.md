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
