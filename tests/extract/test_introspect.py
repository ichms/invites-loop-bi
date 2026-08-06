"""Catalog introspection and the source -> staging type mapping."""

from invites_loop_bi.config import LOAD_TYPE_INCREMENTAL, SOURCE_SYSTEMS, get_extraction_targets
from invites_loop_bi.extract.introspect import (
	Column,
	TableNotFound,
	base_type,
	describe_table,
	quote_ident,
)
from tests.db import source_session
from tests.fakes import table_schema

# ----------------------------------------------------------------- offline


def test_base_type_strips_parameters_and_array_markers():
	assert base_type("character varying(50)") == "character varying"
	assert base_type("numeric(10,2)") == "numeric"
	assert base_type("timestamp(3) without time zone") == "timestamp without time zone"
	assert base_type("text[]") == "text"
	assert base_type("integer[][]") == "integer"
	assert base_type("JSONB") == "jsonb"


def test_builtin_types_are_declared_verbatim_in_staging():
	for data_type in ("integer", "jsonb", "uuid", "numeric(5,1)", "character varying(50)", "interval"):
		assert Column("c", data_type).staging_type == data_type


def test_types_the_warehouse_lacks_become_text():
	# enums, domains and composite types do not exist in the DW
	assert Column("status_cd", "status_type").staging_type == "text"
	assert Column("tags", "relation_type[]").staging_type == "text[]"


def test_array_detection():
	assert Column("c", "text[]").is_array
	assert not Column("c", "text").is_array


def test_quote_ident_accepts_real_names():
	assert quote_ident("tb_user_info") == '"tb_user_info"'
	assert quote_ident("_loaded_at") == '"_loaded_at"'
	# sibc.genetic_trait_info has Korean column names
	assert quote_ident("원활") == '"원활"'


def test_quote_ident_rejects_injection():
	for name in ('users"; DROP TABLE x; --', "a b", "1abc", "", None, "x" * 64):
		try:
			quote_ident(name)
		except ValueError:
			continue
		raise AssertionError(f"{name!r} should have been rejected")


def test_without_drops_columns_from_every_downstream_use():
	schema = table_schema().without(["payload"])
	assert "payload" not in schema.column_names
	assert "payload" not in schema.quoted_columns
	assert len(schema.columns) == 4


def test_without_is_a_no_op_for_an_empty_exclusion():
	schema = table_schema()
	assert schema.without(()) is schema


def test_without_rejects_an_unknown_column():
	try:
		table_schema().without(["not_a_column"])
	except KeyError as exc:
		assert "not_a_column" in str(exc)
	else:
		raise AssertionError("excluding a column that does not exist should raise")


def test_without_refuses_to_drop_a_primary_key_column():
	"""The loader upserts on the key; dropping it would break the merge."""
	try:
		table_schema().without(["user_no"])
	except ValueError as exc:
		assert "primary key" in str(exc)
	else:
		raise AssertionError("excluding a key column should raise")


def test_without_refuses_to_drop_everything():
	try:
		table_schema().without(table_schema().column_names)
	except (ValueError, KeyError):
		pass
	else:
		raise AssertionError("excluding every column should raise")


def test_table_schema_helpers():
	schema = table_schema()
	assert schema.column_names[0] == "user_no"
	assert schema.quoted_columns.startswith('"user_no", "payload"')
	assert schema.qualified_name == '"public"."tb_demo"'
	assert schema.column("payload").data_type == "jsonb"
	try:
		schema.column("nope")
	except KeyError:
		pass
	else:
		raise AssertionError("unknown column should raise")


# --------------------------------------------------------------------- db


def test_every_iccoli_target_is_introspectable():
	with source_session() as source:
		for target in get_extraction_targets("iccoli"):
			schema = describe_table(source, target["schema_name"], target["table_name"])
			assert schema.columns, f"{schema.qualified_name} has no columns"
			if target["load_type"] != LOAD_TYPE_INCREMENTAL:
				# Full refresh truncates and reloads, so it needs no key to merge on.
				continue
			assert schema.primary_key, (
				f"{schema.qualified_name} has no primary key -- an incremental target cannot be "
				f"upserted without one"
			)


def test_every_declared_target_exists_in_its_source():
	"""Catches a typo'd table name in the config before a DAG run does."""
	missing = []
	for system in SOURCE_SYSTEMS:
		with source_session(system) as source:
			for target in get_extraction_targets(system):
				try:
					describe_table(source, target["schema_name"], target["table_name"])
				except TableNotFound:
					missing.append(f"{system}: {target['schema_name']}.{target['table_name']}")
	assert not missing, "targets declared in the config but absent from the source:\n  " + "\n  ".join(missing)


def test_declared_watermark_columns_exist_in_the_source():
	"""
	A watermark column that does not exist makes the table unextractable.

	Both entries below were found by this test; see KNOWN_BAD_WATERMARK_COLS for
	what each was changed to.
	"""
	missing = []
	for system in SOURCE_SYSTEMS:
		with source_session(system) as source:
			for target in get_extraction_targets(system):
				if not target["watermark_col"]:
					continue
				schema = describe_table(source, target["schema_name"], target["table_name"])
				names = set(schema.column_names)
				for key in ("watermark_col", "fallback_watermark_col"):
					column = target[key]
					if column and column not in names:
						missing.append(
							f"{system}: {target['schema_name']}.{target['table_name']} {key}={column!r} "
							f"(has {sorted(n for n in names if n.endswith(('_dt', '_datetime', '_at', '_date')))})"
						)
	assert not missing, "watermark columns declared in the config but absent from the source:\n  " + "\n  ".join(missing)


#: Incremental targets whose source table has no primary key. Left that way on
#: purpose -- the keys were skipped upstream for convenience and their absence
#: does not affect the analysis -- so the loader falls back to deleting the
#: extracted watermark window before inserting it (see StagingLoader._clear_window).
#: The list exists to make the set visible and to catch new arrivals; the test
#: fails both when one appears and when one gains a key, so it cannot rot.
KNOWN_MISSING_PRIMARY_KEY = frozenset({
	"sibc.chat_msgs",
	"sibc.chat_thread_evts",
	"discovery.disc_lifelog_user_activity",
	"discovery.disc_lifelog_user_bloodglucose",
	"discovery.disc_lifelog_user_bloodpressure",
	"discovery.disc_lifelog_user_body_info",
	"discovery.disc_lifelog_user_bodyfat",
	"discovery.disc_lifelog_user_food",
	"discovery.disc_lifelog_user_grip_strength",
	"discovery.disc_lifelog_user_heartrate",
	"discovery.disc_lifelog_user_meal",
	"discovery.disc_lifelog_user_oxygen_saturation",
	"discovery.disc_lifelog_user_sleep_detail",
	"discovery.disc_lifestyle_survey_question_option",
})


def test_incremental_targets_have_a_primary_key():
	found = set()
	for system in SOURCE_SYSTEMS:
		with source_session(system) as source:
			for target in get_extraction_targets(system):
				if target["load_type"] != LOAD_TYPE_INCREMENTAL:
					continue
				schema = describe_table(source, target["schema_name"], target["table_name"])
				if not schema.primary_key:
					found.add(f"{target['schema_name']}.{target['table_name']}")

	new = found - KNOWN_MISSING_PRIMARY_KEY
	fixed = KNOWN_MISSING_PRIMARY_KEY - found
	assert not new, f"new incremental targets without a primary key: {sorted(new)}"
	assert not fixed, f"these now have a primary key -- remove them from KNOWN_MISSING_PRIMARY_KEY: {sorted(fixed)}"


def test_enum_columns_are_mapped_to_text():
	with source_session() as source:
		schema = describe_table(source, "public", "tb_ext_user_preinfo")
		enums = [c for c in schema.columns if c.staging_type != c.data_type]
		assert {c.name for c in enums} == {"relation_cd", "status_cd"}
		assert all(c.staging_type == "text" for c in enums)
		# a uuid is built in, so it survives unchanged
		assert schema.column("ext_user_uuid").staging_type == "uuid"


def test_composite_primary_key_is_ordered_by_key_position():
	with source_session() as source:
		schema = describe_table(source, "public", "tb_action_mapper")
		assert schema.primary_key == ("action_no", "relation_type")


def test_missing_table_raises_table_not_found():
	with source_session() as source:
		try:
			describe_table(source, "public", "tb_does_not_exist_at_all")
		except TableNotFound as exc:
			assert "tb_does_not_exist_at_all" in str(exc)
		else:
			raise AssertionError("a missing table should raise TableNotFound")
