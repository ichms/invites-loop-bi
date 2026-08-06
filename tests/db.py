"""
Database access for the round trip tests.

Connections come from libpq service names (`~/.pg_service.conf`) and can be
overridden per environment:

	INVITES_LOOP_BI_TEST_ICCOLI_DSN        default "service=iccoli"
	INVITES_LOOP_BI_TEST_INVITES_LOOP_DSN  default "service=invites_loop"
	INVITES_LOOP_BI_TEST_DW_DSN            default "service=invites_dw"

`ichms`, `sibc`, `irs` and `discovery` are schemas inside the `invites_loop`
database, so they share one DSN.

**Nothing is ever committed.** The warehouse session hands the pipeline a
connection whose `commit()` does nothing, and the real transaction is rolled back
when the test ends -- so the tests exercise the real DDL / COPY / merge path
against real data while leaving the warehouse exactly as it was.

Tests that need a database are skipped (not failed) when it cannot be reached, so
the offline half of the suite still runs anywhere.
"""

import contextlib
import os

ICCOLI_DSN = os.environ.get("INVITES_LOOP_BI_TEST_ICCOLI_DSN", "service=iccoli")
INVITES_LOOP_DSN = os.environ.get("INVITES_LOOP_BI_TEST_INVITES_LOOP_DSN", "service=invites_loop")
DW_DSN = os.environ.get("INVITES_LOOP_BI_TEST_DW_DSN", "service=invites_dw")

#: Mirrors `config.settings.SOURCE_CONN_IDS`, but as test DSNs.
SOURCE_DSNS = {
	"iccoli": ICCOLI_DSN,
	"ichms": INVITES_LOOP_DSN,
	"sibc": INVITES_LOOP_DSN,
	"irs": INVITES_LOOP_DSN,
	"discovery": INVITES_LOOP_DSN,
}


#: Set to skip every database test, whatever the environment can actually reach.
#: `tests/run_tests.py --offline` and INVITES_LOOP_BI_TEST_OFFLINE=1 both set it.
OFFLINE = os.environ.get("INVITES_LOOP_BI_TEST_OFFLINE", "").lower() in ("1", "true", "yes")


class Skipped(Exception):
	"""Raised instead of failing when a test's prerequisites are missing."""


def skip(reason: str):
	"""
	Skip the current test.

	Only defers to pytest when a pytest run is actually in progress -- merely
	having pytest installed does not mean it is driving, and `pytest.skip()`
	outside a test looks like a failure to any other runner.
	"""
	if os.environ.get("PYTEST_CURRENT_TEST"):
		import pytest

		pytest.skip(reason)
	raise Skipped(reason)


def _psycopg2():
	if OFFLINE:
		skip("offline mode")
	try:
		import psycopg2
	except ImportError:
		skip("psycopg2 is not installed")
	return psycopg2


class RollbackOnlyConnection:
	"""
	Wraps a real connection and swallows `commit()`.

	The pipeline commits after every table; a test needs those commits to be
	no-ops so one rollback at the end can undo the whole run.
	"""

	def __init__(self, conn):
		self._conn = conn
		self.commits = 0

	def cursor(self, *args, **kwargs):
		return self._conn.cursor(*args, **kwargs)

	def commit(self) -> None:
		self.commits += 1

	def rollback(self) -> None:
		self._conn.rollback()

	@property
	def autocommit(self) -> bool:
		return self._conn.autocommit


@contextlib.contextmanager
def source_session(source_system: str = "iccoli"):
	"""Read-only session on the database a source system lives in."""
	psycopg2 = _psycopg2()
	dsn = SOURCE_DSNS[source_system]
	try:
		conn = psycopg2.connect(dsn)
	except psycopg2.Error as exc:
		skip(f"source database unreachable ({dsn}): {exc}".strip())
	conn.set_session(readonly=True)
	try:
		yield conn
	finally:
		conn.rollback()
		conn.close()


@contextlib.contextmanager
def dw_session():
	"""Warehouse session that rolls back everything the test did."""
	psycopg2 = _psycopg2()
	try:
		conn = psycopg2.connect(DW_DSN)
	except psycopg2.Error as exc:
		skip(f"warehouse unreachable ({DW_DSN}): {exc}".strip())
	try:
		yield RollbackOnlyConnection(conn)
	finally:
		conn.rollback()
		conn.close()


@contextlib.contextmanager
def sessions(source_system: str = "iccoli"):
	"""Both sides at once: `with sessions() as (source, dw):`."""
	with source_session(source_system) as source, dw_session() as dw:
		yield source, dw


def reset_staging(dw, source_system: str, schema_name: str, table_name: str) -> None:
	"""
	Restore first-run conditions for one table, inside the test's transaction.

	The warehouse holds committed production loads, so a test that assumes "no
	staging table, no watermark" must drop both first. Everything here is undone
	by the session rollback, so the committed data is untouched.
	"""
	staging = f'stg_{source_system}."{table_name}"'
	with dw.cursor() as cursor:
		cursor.execute("SELECT to_regclass(%s)", (staging,))
		if cursor.fetchone()[0]:
			# CASCADE: since Phase 1 the dbt staging views read these landing
			# tables, so a plain DROP refuses. The views come back with the
			# rollback like everything else in this transaction.
			cursor.execute(f"DROP TABLE {staging} CASCADE")
		cursor.execute("SELECT to_regclass('stg_meta.watermarks')")
		if cursor.fetchone()[0]:
			cursor.execute(
				"DELETE FROM stg_meta.watermarks WHERE source_system=%s AND schema_name=%s AND table_name=%s",
				(source_system, schema_name, table_name),
			)
