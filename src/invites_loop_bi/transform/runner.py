"""
The transform layer is **dbt**, not Python -- see `dbt/` at the repo root
(decision log D-01/D-02). Airflow runs it as a CLI:

	dbt build --project-dir dbt

This module stays only so nobody reintroduces a Python transform runner here;
rows never become Python objects in this pipeline (see extract/introspect.py).
"""
