# Wearable detail models

This directory contains the six source-grain wearable observation facts. dbt
materializes them in `marts_detail` and tags them `wearable_detail`.

They are not part of `daily_core`, are not registered as general Superset
datasets, and are not readable by `superset_reader`. Run them only through the
measured detail procedure with Azure storage checked first, one thread, and
fail-fast. P4 replaces the current full-refresh heart-rate path with the
approved incremental/reconciliation strategy.
