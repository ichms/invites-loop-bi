"""
Shared settings: Airflow connection ids and the staging layout.

All three databases live on the same PostgreSQL server, but they are separate
databases, so every hop still needs its own connection:

	iccoli       -> database `iccoli`,        schema `public`
	ichms        -\\
	sibc          |-> database `invites_loop`, one schema per system
	irs           |
	discovery    -/
	warehouse    -> database `invites_dw`,    schemas `stg_<source_system>` + `stg_meta`
"""

import logging

logger = logging.getLogger(__name__)

# --------------------------------------------------------------- connections
# Airflow connection ids. For local development `setup_env.sh` exports them as
# AIRFLOW_CONN_<UPPERCASED_ID>.
ICCOLI_CONN_ID = "iccoli_db_conn"
INVITES_LOOP_CONN_ID = "invites_loop_db_conn"
OLAP_CONN_ID = "olap_db_conn"

#: Connection each source system is read through. `ichms`, `sibc`, `irs` and
#: `discovery` are schemas *inside* the `invites_loop` database rather than
#: separate databases, so they share one connection.
SOURCE_CONN_IDS = {
	"iccoli": ICCOLI_CONN_ID,
	"ichms": INVITES_LOOP_CONN_ID,
	"sibc": INVITES_LOOP_CONN_ID,
	"irs": INVITES_LOOP_CONN_ID,
	"discovery": INVITES_LOOP_CONN_ID,
}

#: Warehouse connection: staging tables and the watermark metadata table.
STAGING_CONN_ID = OLAP_CONN_ID
META_CONN_ID = OLAP_CONN_ID


def source_conn_id(source_system: str) -> str:
	try:
		return SOURCE_CONN_IDS[source_system]
	except KeyError:
		raise KeyError(
			f"No connection configured for source system {source_system!r}; "
			f"known systems: {sorted(SOURCE_CONN_IDS)}"
		) from None


# ------------------------------------------------------------ staging layout
STAGING_SCHEMA_PREFIX = "stg_"

#: Schema holding `watermarks`, the extraction metadata table.
WATERMARK_SCHEMA = "stg_meta"

#: Bookkeeping column the loader appends to every staging table.
LOADED_AT_COLUMN = "_loaded_at"


def staging_schema_for(source_system: str) -> str:
	"""`iccoli` -> `stg_iccoli`."""
	return f"{STAGING_SCHEMA_PREFIX}{source_system}"


# ------------------------------------------------------------ session sanity
def session_timezone(conn) -> str:
	"""The `TimeZone` setting of a connection's session."""
	with conn.cursor() as cursor:
		cursor.execute("SELECT current_setting('TimeZone')")
		return cursor.fetchone()[0]


def check_timezone_alignment(source_conn, dw_conn) -> bool:
	"""
	Warn when the source and warehouse sessions disagree on their timezone.

	Most source columns are `timestamp with time zone`, which carries its offset
	through `COPY` and is therefore immune.  A few (e.g. iccoli's
	`tb_activity_user_log`) are naive `timestamp`: their watermark values land in
	`stg_meta.watermarks`, a `timestamptz` column where the session timezone is
	what gives a naive value meaning, and are later fed back as a query bound.
	That round trip is only exact while both sessions agree.
	"""
	source_tz = session_timezone(source_conn)
	dw_tz = session_timezone(dw_conn)
	if source_tz != dw_tz:
		logger.warning(
			"Source session timezone (%s) differs from the warehouse (%s). Watermarks taken "
			"from naive `timestamp` columns may be off by the difference -- align both sessions.",
			source_tz,
			dw_tz,
		)
		return False
	return True
