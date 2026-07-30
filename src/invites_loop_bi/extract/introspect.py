"""
Source table introspection.

The staging loader needs two things the target config does not carry: the column
list with types (to create the staging table) and the primary key (to upsert
re-delivered rows).  Both are read straight from the source catalog, so no DDL
has to be mirrored by hand across ~100 tables.

Type mapping is almost a no-op, because rows travel between the two databases as
`COPY ... CSV` text -- PostgreSQL's own representation -- and never become Python
objects.  The one thing that has to be translated is types the warehouse does not
have: enums, domains, composite types, extension types (PostGIS, citext, ...).
Those become `text` in staging, and their CSV text loads into a `text` column
unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

_PARAMS_RE = re.compile(r"\(\s*\d+(?:\s*,\s*\d+)?\s*\)")
# \w so non-ASCII letters pass (sibc.genetic_trait_info has Korean column names);
# quotes, whitespace and punctuation still fail, which is what quoting relies on.
_IDENTIFIER_RE = re.compile(r"^[^\W\d$][\w$]{0,62}$")

#: Built-in types the warehouse can declare exactly as the source does.
BUILTIN_TYPES = frozenset({
	"smallint",
	"integer",
	"bigint",
	"boolean",
	"real",
	"double precision",
	"numeric",
	"decimal",
	"text",
	"character varying",
	"character",
	"date",
	"timestamp without time zone",
	"timestamp with time zone",
	"time without time zone",
	"time with time zone",
	"interval",
	"json",
	"jsonb",
	"uuid",
	"bytea",
	"inet",
	"cidr",
	"macaddr",
	"bit",
	"bit varying",
	"money",
	"xml",
})

_COLUMNS_SQL = """
SELECT a.attname,
       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
       a.attnotnull
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s
  AND c.relname = %s
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
"""

_PRIMARY_KEY_SQL = """
SELECT a.attname
FROM pg_catalog.pg_index i
JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
WHERE n.nspname = %s
  AND c.relname = %s
  AND i.indisprimary
ORDER BY k.ord;
"""


class TableNotFound(LookupError):
	"""Raised by `describe_table` when the relation is not in the catalog."""


def quote_ident(name: str) -> str:
	"""
	Quote a schema / table / column name.

	Identifiers cannot be bound as `%s` parameters, so names coming from the
	target config or the catalog are validated against a conservative pattern
	first and only then interpolated into SQL text.
	"""
	if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
		raise ValueError(f"Unsupported SQL identifier: {name!r}")
	return f'"{name}"'


def base_type(data_type: str) -> str:
	"""`character varying(50)` -> `character varying`, `text[]` -> `text`."""
	stripped = _PARAMS_RE.sub("", data_type).strip().lower()
	while stripped.endswith("[]"):
		stripped = stripped[:-2].strip()
	return stripped


@dataclass(frozen=True)
class Column:
	name: str
	#: `pg_catalog.format_type` output, e.g. `character varying(50)`, `jsonb`, `text[]`.
	data_type: str
	not_null: bool = False

	@property
	def is_array(self) -> bool:
		return self.data_type.strip().endswith("[]")

	@property
	def base_type(self) -> str:
		return base_type(self.data_type)

	@property
	def staging_type(self) -> str:
		"""Column type to declare in the staging table."""
		if self.base_type in BUILTIN_TYPES:
			return self.data_type
		# Enum / domain / composite / extension type: no such type in the DW.
		return "text[]" if self.is_array else "text"

	@property
	def quoted_name(self) -> str:
		return quote_ident(self.name)


@dataclass(frozen=True)
class TableSchema:
	schema_name: str
	table_name: str
	columns: tuple[Column, ...]
	primary_key: tuple[str, ...] = ()

	@property
	def qualified_name(self) -> str:
		return f"{quote_ident(self.schema_name)}.{quote_ident(self.table_name)}"

	@property
	def column_names(self) -> list[str]:
		return [column.name for column in self.columns]

	@property
	def quoted_columns(self) -> str:
		"""Explicit column list -- never `SELECT *`, so column order is pinned."""
		return ", ".join(column.quoted_name for column in self.columns)

	def column(self, name: str) -> Column:
		for column in self.columns:
			if column.name == name:
				return column
		raise KeyError(f"{self.qualified_name} has no column {name!r}")

	def without(self, column_names) -> TableSchema:
		"""
		Drop columns from the schema, so they are never read, staged or stored.

		Used for payload columns that dwarf the rest of the table -- e.g.
		`disc_lifelog_user_meal.meal_data` averages 557 kB per row (base64 images)
		while every other column together is 44 bytes, turning a 21 GB extract into
		a 1.5 MB one.
		"""
		excluded = tuple(column_names)
		if not excluded:
			return self

		unknown = [name for name in excluded if name not in set(self.column_names)]
		if unknown:
			raise KeyError(f"{self.qualified_name} has no column(s) {unknown} to exclude")

		in_key = [name for name in excluded if name in self.primary_key]
		if in_key:
			raise ValueError(
				f"cannot exclude {in_key} from {self.qualified_name}: they are part of its primary key, "
				f"which the loader upserts on"
			)

		kept = tuple(column for column in self.columns if column.name not in set(excluded))
		if not kept:
			raise ValueError(f"excluding {list(excluded)} would leave {self.qualified_name} with no columns")
		return replace(self, columns=kept)


def describe_table(conn, schema_name: str, table_name: str) -> TableSchema:
	"""
	Read a table's columns and primary key from the PostgreSQL catalog.

	Raises `TableNotFound` when the relation does not exist or is not visible to
	this connection -- which is also how a typo in the target config surfaces.
	"""
	with conn.cursor() as cursor:
		cursor.execute(_COLUMNS_SQL, (schema_name, table_name))
		columns = tuple(Column(name=row[0], data_type=row[1], not_null=row[2]) for row in cursor.fetchall())

		if not columns:
			raise TableNotFound(f"{schema_name}.{table_name} does not exist or is not visible to this connection")

		cursor.execute(_PRIMARY_KEY_SQL, (schema_name, table_name))
		primary_key = tuple(row[0] for row in cursor.fetchall())

	return TableSchema(
		schema_name=schema_name,
		table_name=table_name,
		columns=columns,
		primary_key=primary_key,
	)
