"""
Opening the source and warehouse connections, inside Airflow or outside it.

Connection ids come from `config.settings`. Resolution order:

1. `AIRFLOW_CONN_<ID>` in the environment -- what `setup_env.sh` exports for local
   development, and what a worker sees for env-defined connections. Used directly
   as a libpq DSN, so no Airflow import is needed to run the pipeline by hand.
2. `PostgresHook`, which is how connections stored in the Airflow metadata
   database are resolved on a worker.

Both hand back a plain psycopg2 connection with autocommit **off**: the loader
needs its temp table, delete and insert to share one transaction, and the
extractor's COPY has to see one consistent snapshot.
"""

import contextlib
import logging
import os

from invites_loop_bi.config.settings import STAGING_CONN_ID, source_conn_id

logger = logging.getLogger(__name__)


def dsn_from_env(conn_id: str) -> str | None:
	"""The `AIRFLOW_CONN_*` URI for a connection id, if one is exported."""
	return os.environ.get(f"AIRFLOW_CONN_{conn_id.upper()}")


def connect(conn_id: str, *, readonly: bool = False):
	"""Open a psycopg2 connection for an Airflow connection id."""
	dsn = dsn_from_env(conn_id)
	if dsn:
		import psycopg2

		conn = psycopg2.connect(dsn)
	else:
		from airflow.providers.postgres.hooks.postgres import PostgresHook

		logger.debug("No AIRFLOW_CONN_%s in the environment; falling back to PostgresHook", conn_id.upper())
		conn = PostgresHook(postgres_conn_id=conn_id).get_conn()

	conn.autocommit = False
	if readonly:
		# Belt and braces: the pipeline must never write to a source database.
		conn.set_session(readonly=True)
	return conn


def source_connection(source_system: str):
	"""Read-only connection to the database a source system lives in."""
	return connect(source_conn_id(source_system), readonly=True)


def warehouse_connection():
	"""Read-write connection to the warehouse (staging tables + `stg_meta`)."""
	return connect(STAGING_CONN_ID)


@contextlib.contextmanager
def open_connections(source_system: str):
	"""
	Both connections for one source system, closed on the way out.

	psycopg2 connections are not context managers in this sense -- `with conn:`
	manages a transaction, not the connection -- hence the explicit close.
	"""
	source = source_connection(source_system)
	try:
		warehouse = warehouse_connection()
	except BaseException:
		source.close()
		raise

	try:
		yield source, warehouse
	finally:
		source.close()
		warehouse.close()
