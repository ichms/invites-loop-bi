"""
Registry of the declarative extraction targets.

Each `<system>_targets.py` module exports the tables to pull from that source
system.  Two flavours exist:

* `<SYSTEM>_EXTRACTION_TARGETS`   -- watermark based incremental tables.
* `<SYSTEM>_FULL_REFRESH_TARGETS` -- small reference/meta tables that are
	truncated and reloaded on every run.

`get_extraction_targets()` merges both lists for a source system and normalises
every entry so downstream code (the extractors) can rely on a fixed shape:

	{
		"source_system":          "iccoli",
		"schema_name":            "public",
		"table_name":             "tb_user_info",
		"load_type":              "incremental" | "full_refresh",
		"watermark_col":          "update_datetime" | None,
		"fallback_watermark_col": "create_datetime" | None,
		"exclude_columns":        ("meal_data",),   # never read, staged or stored
		"row_filter":             "user_no IN (...)" | None,
		"lookback_days":          30 | None,       # re-read this far below the watermark
	}

`exclude_columns` is optional and exists for payload columns that dwarf the rest
of a table; see `disc_lifelog_user_meal` in `discovery_targets.py`.

`lookback_days` widens the incremental window *downwards*, re-reading rows that
sit below the last watermark. It exists for sources that write rows with a
**backdated** watermark -- wearables sync late, so a watch uploads samples
stamped days ago -- which a plain `watermark_expr > last_watermark` predicate can
never see again. Replay is safe: the loader upserts on the primary key, or (for
the keyless tables) deletes exactly the window it is about to insert, reusing
this same widened predicate. Cost is a wider read every run, so it is declared
per table rather than switched on globally.

`row_filter` is an optional SQL predicate evaluated **in the source database**;
rows that do not match never leave the source system. It exists for data
minimisation (see `LOOP_USERS_ONLY` in `iccoli_targets.py`) and must be
self-contained SQL: no `%s` placeholders, and any literal `%` doubled to `%%`,
because the extraction query is bound with `mogrify()`.
"""

import logging

from invites_loop_bi.config.discovery_targets import (
	DISCOVERY_EXTRACTION_TARGETS,
	DISCOVERY_FULL_REFRESH_TARGETS,
)
from invites_loop_bi.config.iccoli_targets import (
	ICCOLI_EXTRACTION_TARGETS,
	ICCOLI_FULL_REFRESH_TARGETS,
)
from invites_loop_bi.config.ichms_targets import (
	ICHMS_EXTRACTION_TARGETS,
	ICHMS_FULL_REFRESH_TARGETS,
)
from invites_loop_bi.config.irs_targets import (
	IRS_EXTRACTION_TARGETS,
	IRS_FULL_REFRESH_TARGETS,
)
from invites_loop_bi.config.sibc_targets import (
	SIBC_EXTRACTION_TARGETS,
	SIBC_FULL_REFRESH_TARGETS,
)

logger = logging.getLogger(__name__)

# Load strategies. `load_type` is only spelled out in the *_FULL_REFRESH_TARGETS
# entries; anything without one is incremental.
LOAD_TYPE_INCREMENTAL = "incremental"
LOAD_TYPE_FULL_REFRESH = "full_refresh"

#: Watermark based targets, keyed by source system.
EXTRACTION_TARGETS: dict[str, list[dict]] = {
	"iccoli": ICCOLI_EXTRACTION_TARGETS,
	"ichms": ICHMS_EXTRACTION_TARGETS,
	"sibc": SIBC_EXTRACTION_TARGETS,
	"irs": IRS_EXTRACTION_TARGETS,
	"discovery": DISCOVERY_EXTRACTION_TARGETS,
}

#: Truncate & reload targets, keyed by source system.
FULL_REFRESH_TARGETS: dict[str, list[dict]] = {
	"iccoli": ICCOLI_FULL_REFRESH_TARGETS,
	"ichms": ICHMS_FULL_REFRESH_TARGETS,
	"sibc": SIBC_FULL_REFRESH_TARGETS,
	"irs": IRS_FULL_REFRESH_TARGETS,
	"discovery": DISCOVERY_FULL_REFRESH_TARGETS,
}

SOURCE_SYSTEMS = tuple(EXTRACTION_TARGETS)


def _normalise(source_system: str, target: dict, load_type: str) -> dict:
	missing = {"schema_name", "table_name"} - target.keys()
	if missing:
		raise ValueError(f"[{source_system}] extraction target is missing {sorted(missing)}: {target}")

	if load_type == LOAD_TYPE_INCREMENTAL and not target.get("watermark_col"):
		raise ValueError(
			f"[{source_system}] {target['schema_name']}.{target['table_name']} is incremental "
			f"but declares no 'watermark_col'"
		)

	lookback_days = target.get("lookback_days")
	if lookback_days is not None:
		if not isinstance(lookback_days, int | float) or isinstance(lookback_days, bool) or lookback_days < 0:
			raise ValueError(
				f"[{source_system}] {target['schema_name']}.{target['table_name']} declares "
				f"'lookback_days'={lookback_days!r}; it must be a non-negative number of days"
			)
		# A full refresh already re-reads everything, so a lookback is a no-op there.
		# Silently ignoring it would hide a config mistake.
		if target.get("load_type", load_type) == LOAD_TYPE_FULL_REFRESH:
			raise ValueError(
				f"[{source_system}] {target['schema_name']}.{target['table_name']} is full_refresh "
				f"but declares 'lookback_days'; the whole table is read on every run already"
			)

	return {
		"source_system": source_system,
		"schema_name": target["schema_name"],
		"table_name": target["table_name"],
		"load_type": target.get("load_type", load_type),
		"watermark_col": target.get("watermark_col"),
		"fallback_watermark_col": target.get("fallback_watermark_col"),
		"exclude_columns": tuple(target.get("exclude_columns") or ()),
		"row_filter": target.get("row_filter") or None,
		"lookback_days": lookback_days,
	}


def get_extraction_targets(
	source_system: str,
	*,
	include_incremental: bool = True,
	include_full_refresh: bool = True,
) -> list[dict]:
	"""
	Return the normalised extraction targets for `source_system`.

	Duplicate `(schema_name, table_name)` entries are dropped -- the first
	declaration wins -- and logged, since a table can only carry one watermark.
	"""
	if source_system not in EXTRACTION_TARGETS:
		raise KeyError(f"Unknown source system {source_system!r}; known systems: {list(SOURCE_SYSTEMS)}")

	declared: list[dict] = []
	if include_incremental:
		declared += [_normalise(source_system, t, LOAD_TYPE_INCREMENTAL) for t in EXTRACTION_TARGETS[source_system]]
	if include_full_refresh:
		declared += [
			_normalise(source_system, t, LOAD_TYPE_FULL_REFRESH)
			for t in FULL_REFRESH_TARGETS.get(source_system, [])
		]

	targets: dict[tuple[str, str], dict] = {}
	for target in declared:
		key = (target["schema_name"], target["table_name"])
		if key in targets:
			logger.warning(
				"[%s] duplicate extraction target %s.%s declared -- keeping the first one "
				"(watermark_col=%s, dropped watermark_col=%s)",
				source_system,
				*key,
				targets[key]["watermark_col"],
				target["watermark_col"],
			)
			continue
		targets[key] = target

	return list(targets.values())


def get_all_extraction_targets() -> dict[str, list[dict]]:
	"""Normalised targets for every known source system."""
	return {system: get_extraction_targets(system) for system in SOURCE_SYSTEMS}
