from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class WatermarkStore:
	"""
	What the extractor needs from watermark bookkeeping.

	`WatermarkManager` is the real implementation; tests supply an in-memory stub
	with the same three methods.
	"""

	def get_last_watermark(
		self, source_system: str, schema_name: str, table_name: str
	) -> datetime | None:
		raise NotImplementedError

	def update_watermark(
		self,
		source_system: str,
		schema_name: str,
		table_name: str,
		new_watermark: datetime,
		status: str = "SUCCESS",
		row_count: int | None = None,
	) -> None:
		raise NotImplementedError

	def mark_failed(
		self, source_system: str, schema_name: str, table_name: str, error: str | None = None
	) -> None:
		raise NotImplementedError


class WatermarkManager(WatermarkStore):
	"""
	Through the metadata table in the staging database (`stg_meta.watermarks`),
	watermark timestamps are queried and updated for each source and schema.

	`watermark_value` is always a value that came out of the source table itself
	(the highest watermark column value that has been loaded successfully), never
	a clock reading taken on the Airflow worker.  That keeps the extractor free of
	clock-skew problems, but it does assume the source DB and the DW agree on
	their session timezone when a source column is a naive `timestamp`.
	"""
	def __init__(self, meta_db_conn, ensure_table: bool = True):
		"""
		:param meta_db_conn: PostgreSQL / DW database connection objects (psycopg2, psycopg, etc.)
		:param ensure_table: create the metadata schema/table if missing. Pass False
			for read-only callers (a dry run must not write to the warehouse); the
			lookup then reports "no watermark" while the table does not exist yet.
		"""
		self.conn = meta_db_conn
		self._ensured = ensure_table
		if ensure_table:
			self._ensure_watermark_table()

	def _watermark_table_exists(self) -> bool:
		with self.conn.cursor() as cursor:
			cursor.execute("SELECT to_regclass('stg_meta.watermarks') IS NOT NULL")
			return bool(cursor.fetchone()[0])

	def _ensure_watermark_table(self) -> None:
		"""
		Automatically creates the watermark metadata schema and tables if they do not exist.
		"""
		create_table_sql = """
		CREATE SCHEMA IF NOT EXISTS stg_meta;

		CREATE TABLE IF NOT EXISTS stg_meta.watermarks (
			source_system    VARCHAR(50)  NOT NULL,  -- e.g., 'iccoli', 'invites_loop'
			schema_name      VARCHAR(50)  NOT NULL,  -- e.g., 'public', 'ichms', 'sibc'
			table_name       VARCHAR(100) NOT NULL,  -- e.g., 'user_activity_logs'
			watermark_value  TIMESTAMPTZ  NULL,      -- The cutoff point for the last successful extraction
			last_status      VARCHAR(20)  NOT NULL DEFAULT 'SUCCESS',
			last_error       TEXT         NULL,      -- Error message of the last failed run
			row_count        BIGINT       NULL,      -- Rows extracted by the last successful run
			updated_at       TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY (source_system, schema_name, table_name)
		);
		"""

		with self.conn.cursor() as cursor:
			cursor.execute(create_table_sql)
		self.conn.commit()


	def get_last_watermark(self, source_system: str, schema_name: str, table_name: str) -> datetime | None:
		"""
		Retrieves the last successful watermark timestamp for the specified table.
		If no record exists, returns None to trigger an initial full load.

		The status is deliberately *not* part of the filter: `watermark_value` only
		ever moves forward on a successful load, so after a failed run it still
		holds the last good cutoff.  Filtering failed rows out here would silently
		turn the next run into a full reload of the whole table.
		"""

		if not self._ensured and not self._watermark_table_exists():
			logger.info(f"DB: {source_system} [{schema_name}.{table_name}] No watermark table yet (Full Load Mode)")
			return None

		query = """
		SELECT watermark_value, last_status
		FROM stg_meta.watermarks
		WHERE source_system = %s
		  AND schema_name = %s
		  AND table_name = %s;
		"""
		with self.conn.cursor() as cursor:
			cursor.execute(query, (source_system, schema_name, table_name))
			result = cursor.fetchone()

			if result and result[0]:
				watermark, status = result
				if status != "SUCCESS":
					logger.warning(
						f"DB: {source_system} [{schema_name}.{table_name}] Last run ended with status "
						f"'{status}'; resuming from the last good watermark: {watermark}"
					)
				else:
					logger.info(f"DB: {source_system} [{schema_name}.{table_name}] Existing watermark lookup successful: {watermark} (Incremental Mode)")
				return watermark

			logger.info(f"DB: {source_system} [{schema_name}.{table_name}] No existing watermark (Full Load Mode)")
			return None


	def update_watermark(
		self,
		source_system: str,
		schema_name: str,
		table_name: str,
		new_watermark: datetime,
		status: str = "SUCCESS",
		row_count: int | None = None,
	) -> None:
		"""
		After the pipeline executes successfully, upsert (insert/update) the new watermark timestamp.
		"""
		upsert_sql = """
		INSERT INTO stg_meta.watermarks (source_system, schema_name, table_name, watermark_value, last_status, last_error, row_count, updated_at)
		VALUES (%s, %s, %s, %s, %s, NULL, %s, CURRENT_TIMESTAMP)
		ON CONFLICT (source_system, schema_name, table_name)
		DO UPDATE SET
			watermark_value = EXCLUDED.watermark_value,
			last_status = EXCLUDED.last_status,
			last_error = EXCLUDED.last_error,
			row_count = EXCLUDED.row_count,
			updated_at = EXCLUDED.updated_at;
		"""

		with self.conn.cursor() as cursor:
			cursor.execute(upsert_sql, (source_system, schema_name, table_name, new_watermark, status, row_count))
		self.conn.commit()

		logger.info(f"DB: {source_system} [{schema_name}.{table_name}] Watermark update complete: {new_watermark} (Status: {status})")


	def mark_failed(self, source_system: str, schema_name: str, table_name: str, error: str | None = None) -> None:
		"""
		Flag the last run as failed **without touching `watermark_value`**, so the
		next run picks up from the last successfully loaded cutoff and replays the
		rows that never made it into staging.
		"""
		upsert_sql = """
		INSERT INTO stg_meta.watermarks (source_system, schema_name, table_name, watermark_value, last_status, last_error, updated_at)
		VALUES (%s, %s, %s, NULL, 'FAILED', %s, CURRENT_TIMESTAMP)
		ON CONFLICT (source_system, schema_name, table_name)
		DO UPDATE SET
			last_status = 'FAILED',
			last_error = EXCLUDED.last_error,
			updated_at = EXCLUDED.updated_at;
		"""

		with self.conn.cursor() as cursor:
			cursor.execute(upsert_sql, (source_system, schema_name, table_name, error))
		self.conn.commit()

		logger.error(f"DB: {source_system} [{schema_name}.{table_name}] Extraction marked as FAILED: {error}")
