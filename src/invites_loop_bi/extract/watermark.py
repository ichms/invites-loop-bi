from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class WatermarkManager():
	"""
	Through the metadata table in the staging database (`stg_meta.watermarks`), 
	watermark timestamps are queried and updated for each source and schema.
	"""
	def __init__(self, meta_db_conn):
		"""
		:param db_conn: PostgreSQL / DW database connection objects (psycopg2, psycopg, etc.)
		"""
		self.conn = meta_db_conn
		self._ensure_watermark_table()

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
            watermark_value  TIMESTAMP    NULL,      -- The cutoff point for the last successful extraction
            last_status      VARCHAR(20)  NOT NULL DEFAULT 'SUCCESS',
            updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
		"""

		query = """
		SELECT watermark_value
		FROM stg_meta.watermarks
		WHERE source_system = %s
		  AND schema_name = %s 
          AND table_name = %s 
          AND last_status = 'SUCCESS';
		"""
		with self.conn.cursor() as cursor:
			cursor.execute(query, (source_system, schema_name, table_name))
			result = cursor.fetchone()

			if result and result[0]:
				logger.info(f"DB: {source_system} [{schema_name}.{table_name}] Existing watermark lookup successful: {result[0]} (Incremental Mode)")
				return result[0]

			logger.info(f"DB: {source_system} [{schema_name}.{table_name}] No existing watermark (Full Load Mode)")
			return None

	
	def update_watermark(self, source_system: str, schema_name: str, table_name: str, new_watermark: datetime, status: str = "SUCCESS") -> None:
		"""
		After the pipeline executes successfully, upsert (insert/update) the new watermark timestamp.
		"""
		upsert_sql = """
		INSERT INTO stg_meta.watermarks (source_system, schema_name, table_name, watermark_value, last_status, updated_at)
		VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
		ON CONFLICT (source_system, schema_name, table_name) 
		DO UPDATE SET 
			watermark_value = EXCLUDED.watermark_value,
			last_status = EXCLUDED.last_status,
			updated_at = EXCLUDED.updated_at;
		"""

		with self.conn.cursor() as cursor:
			cursor.execute(upsert_sql, (source_system, schema_name, table_name, new_watermark, status))
			self.conn.commit()

		logger.info(f"DB: {source_system} [{schema_name}.{table_name}] Watermark update complete: {new_watermark} (Status: {status})")





