# apache/superset ships "lean" since 3.x: no database drivers at all, not even
# for its own metadata DB. This adds the one driver both databases here need
# (app DB and warehouse are PostgreSQL 17). Superset's own docs recommend
# exactly this derived-image route; a runtime `pip install` would re-download
# on every container recreation and break offline starts.
FROM apache/superset:6.1.0

# The venv is uv-built and has no pip; uv itself is in the image.
USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache psycopg2-binary==2.9.10
USER superset
