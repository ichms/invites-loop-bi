# Superset configuration — the counterpart of the MB_* environment block in
# the Metabase compose file. Superset takes a Python module, not env vars;
# this file is mounted read-only into the containers and pointed at by
# SUPERSET_CONFIG_PATH.

import os

# Refuses to start on the default key, by design; generated into .env.
SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

# Application database (dashboards, charts, users, warehouse credentials).
# Never SQLite — same reasoning as Metabase's D-13 "never H2".
SQLALCHEMY_DATABASE_URI = (
	"postgresql+psycopg2://{user}:{pw}@superset-app-db:5432/{db}".format(
		user=os.environ.get("SS_DB_USER", "superset"),
		pw=os.environ["SS_DB_PASS"],
		db=os.environ.get("SS_DB_DBNAME", "superset_app"),
	)
)

# --- correctness, not cosmetics -------------------------------------------
# There is NO Superset equivalent of MB_REPORT_TIMEZONE (D-18). Time grains
# compile to date_trunc() in the warehouse session, so KST is enforced where
# it belongs: `ALTER ROLE superset_reader SET timezone = 'Asia/Seoul'` in
# sql/01_superset_reader_role.sql. Nothing to configure here — recorded so
# nobody goes looking for the missing setting.

# Matches the role's statement_timeout (120s). The DB kills the query; these
# stop the UI from waiting on a corpse.
SQLLAB_TIMEOUT = 120
SUPERSET_WEBSERVER_TIMEOUT = 120

# GUI exploration guard, same spirit as the role timeouts.
ROW_LIMIT = 5000
SQL_MAX_ROW = 100_000

# Korean-first, like MB_SITE_LOCALE=ko.
BABEL_DEFAULT_LOCALE = "ko"
LANGUAGES = {
	"ko": {"flag": "kr", "name": "Korean"},
	"en": {"flag": "us", "name": "English"},
}

# Single-node laptop deploy: in-process caches, no Redis/Celery. If this ever
# grows a scheduler or alerts/reports, that is the moment to add them.
CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}
DATA_CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}
FILTER_STATE_CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache"}
EXPLORE_FORM_DATA_CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache"}

FEATURE_FLAGS = {
	# Off: needs Celery workers this deploy does not have.
	"ALERT_REPORTS": False,
}
