from datetime import datetime
import polars as pl

from invites_loop_bi.extract.watermark import WatermarkManager


class BaseExtractor:
	def __init__(self, source_conn, meta_conn, source_system: str, schema_name: str, table_name: str, watermark_col: str):
		# 1. Source DB connection for data extraction (Read-Only)
		self.source_conn = source_conn
		self.source_system = source_system
		self.schema_name = schema_name
		self.table_name = table_name
		self.watermark_col = watermark_col # 'create_datetime' or 'update_datetime'
		
		# 2. Meta/DW DB connection for watermark management (READ-Write)
		self.wm_manager = WatermarkManager(meta_db_conn=meta_conn)

	
	def extract(self):
		# 1. Record the extraction start time (current time)
		execution_time = datetime.now()

		# 2. Watermark Lookup
		last_wm = self.wm_manager.get_last_watermark(self.source_system, self.schema_name, self.table_name)

		# 3. Dynamic generation of SQL query conditions
		if last_wm is None:
			# Round 1: Full data extraction
			query = f"SELECT * FROM {self.table_name} WHERE {self.watermark_col} <= '{execution_time}'"
		else:
			# Round 2: Incremental extraction
			query = f"""
				SELECT * FROM {self.schema_name}.{self.table_name}
				WHERE {self.watermark_col} > '{last_wm}'
				  AND {self.watermark_col} <= '{execution_time}'
			"""


if __name__ == "__main__":
	print("yo")