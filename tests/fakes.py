"""Stand-ins that let the offline half of the suite run without any database."""

from datetime import datetime

from invites_loop_bi.extract.introspect import Column, TableSchema
from invites_loop_bi.extract.watermark import WatermarkStore


class StubWatermarkManager(WatermarkStore):
	"""A `WatermarkManager` that keeps its state in memory."""

	def __init__(self, watermark: datetime | None = None):
		self.watermark = watermark
		self.updates: list[tuple] = []
		self.failures: list[tuple] = []

	def get_last_watermark(self, source_system, schema_name, table_name):
		return self.watermark

	def update_watermark(self, source_system, schema_name, table_name, new_watermark, status="SUCCESS", row_count=None):
		self.updates.append((source_system, schema_name, table_name, new_watermark, status, row_count))
		self.watermark = new_watermark

	def mark_failed(self, source_system, schema_name, table_name, error=None):
		self.failures.append((source_system, schema_name, table_name, error))


class NullConnection:
	"""
	Satisfies the loader's constructor without allowing any database access.

	Used for the SQL-generation tests: touching the connection is a bug there, so
	`cursor()` fails loudly rather than silently doing nothing.
	"""

	autocommit = False

	def cursor(self, *args, **kwargs):
		raise AssertionError("this test must not touch the database")

	def commit(self) -> None:
		raise AssertionError("this test must not touch the database")

	def rollback(self) -> None:
		pass


class RecordingCursor:
	def __init__(self, connection):
		self.connection = connection

	def __enter__(self):
		return self

	def __exit__(self, *exc_info):
		return False

	def execute(self, sql, params=None):
		self.connection.executed.append((" ".join(sql.split()), params))

	def fetchone(self):
		return self.connection.results.pop(0) if self.connection.results else None

	def fetchall(self):
		results, self.connection.results = self.connection.results, []
		return results

	def close(self):
		pass


class RecordingConnection:
	"""
	Records the SQL it is given and replays canned results.

	Enough of the DB-API to exercise the watermark bookkeeping without a database.
	"""

	autocommit = False

	def __init__(self, results: list | None = None):
		self.executed: list[tuple[str, tuple | None]] = []
		self.results = list(results or [])
		self.commits = 0
		self.rollbacks = 0

	def cursor(self, *args, **kwargs):
		return RecordingCursor(self)

	def commit(self) -> None:
		self.commits += 1

	def rollback(self) -> None:
		self.rollbacks += 1

	def statements(self) -> list[str]:
		return [sql for sql, _ in self.executed]


def table_schema(
	table_name: str = "tb_demo",
	schema_name: str = "public",
	columns: tuple[tuple[str, str], ...] = (
		("user_no", "integer"),
		("payload", "jsonb"),
		("status_cd", "status_type"),
		("update_datetime", "timestamp with time zone"),
		("create_datetime", "timestamp with time zone"),
	),
	primary_key: tuple[str, ...] = ("user_no",),
) -> TableSchema:
	"""A `TableSchema` shaped like the real sources, without asking a catalog."""
	return TableSchema(
		schema_name=schema_name,
		table_name=table_name,
		columns=tuple(Column(name=name, data_type=data_type) for name, data_type in columns),
		primary_key=primary_key,
	)
