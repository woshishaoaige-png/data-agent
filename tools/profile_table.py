"""Profile a table or sample rows for data-agent exploration.

The catalog describes schema and high-level coverage. This profiler inspects
actual values so an agent can notice nulls, low-cardinality dimensions, date
gaps, suspicious metrics, and duplicate natural keys before doing analysis.
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from numbers import Number
from pathlib import Path
from statistics import mean

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))
from db import get_engine  # noqa: E402
from config import get_active_datasource  # noqa: E402
from dialects import get_dialect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

DATE_HINTS = ("date", "time", "month", "quarter", "year")
ID_HINTS = ("id", "code", "symbol", "ts_code")
METRIC_HINTS = (
    "amount", "money", "price", "close", "open", "high", "low", "pct", "rate",
    "ratio", "count", "num", "volume", "turnover", "balance", "net", "buy", "sell",
)


@dataclass
class ColumnProfile:
    name: str
    kind: str
    row_count: int
    null_count: int
    distinct_count: int
    top_values: list[dict]
    stats: dict

    def as_dict(self):
        return {
            "name": self.name,
            "kind": self.kind,
            "null_count": self.null_count,
            "null_rate": self.null_count / self.row_count if self.row_count else 0,
            "distinct_count": self.distinct_count,
            "distinct_rate": self.distinct_count / self.row_count if self.row_count else 0,
            "top_values": self.top_values,
            "stats": self.stats,
        }


def normalize_rows(rows):
    normalized = []
    for row in rows:
        if hasattr(row, "_mapping"):
            normalized.append(dict(row._mapping))
        else:
            normalized.append(dict(row))
    return normalized


def infer_kind(name, values):
    lname = name.lower()
    non_null = [v for v in values if v is not None]
    if any(hint in lname for hint in DATE_HINTS):
        return "temporal"
    if any(hint == lname or lname.endswith("_" + hint) or hint in lname for hint in ID_HINTS):
        return "identifier"
    if non_null and all(isinstance(v, bool) for v in non_null):
        return "boolean"
    if non_null and all(isinstance(v, Number) and not isinstance(v, bool) for v in non_null):
        if any(hint in lname for hint in METRIC_HINTS):
            return "metric"
        return "numeric"
    distinct_count = len(set(str(v) for v in non_null))
    if non_null and distinct_count <= max(20, len(non_null) // 2):
        return "dimension"
    return "text"


def _jsonable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def profile_column(name, rows):
    values = [row.get(name) for row in rows]
    row_count = len(rows)
    non_null = [v for v in values if v is not None]
    null_count = row_count - len(non_null)
    kind = infer_kind(name, values)
    serialized = [_jsonable(v) for v in non_null]
    counts = Counter(str(v) for v in serialized)
    top_values = [{"value": value, "count": count} for value, count in counts.most_common(5)]
    stats = {}

    if non_null and all(isinstance(v, Number) and not isinstance(v, bool) for v in non_null):
        nums = [float(v) for v in non_null]
        stats = {
            "min": min(nums),
            "max": max(nums),
            "avg": mean(nums),
            "zero_count": sum(1 for v in nums if v == 0),
            "negative_count": sum(1 for v in nums if v < 0),
        }
    elif kind == "temporal" and serialized:
        ordered = sorted(str(v) for v in serialized)
        stats = {"min": ordered[0], "max": ordered[-1]}
    elif non_null and all(isinstance(v, str) for v in non_null):
        lengths = [len(v) for v in non_null]
        stats = {
            "min_length": min(lengths),
            "max_length": max(lengths),
            "avg_length": mean(lengths),
            "empty_string_count": sum(1 for v in non_null if v == ""),
            "trim_issue_count": sum(1 for v in non_null if v != v.strip()),
        }

    return ColumnProfile(
        name=name,
        kind=kind,
        row_count=row_count,
        null_count=null_count,
        distinct_count=len(counts),
        top_values=top_values,
        stats=stats,
    )


def _infer_key_columns(columns):
    cols = set(columns)
    for candidate in (("trade_date", "ts_code"), ("trade_date", "code"), ("date", "code")):
        if set(candidate).issubset(cols):
            return list(candidate)
    for candidate in ("ts_code", "code", "stock_code", "id"):
        if candidate in cols:
            return [candidate]
    return []


def profile_rows(rows, table=None, key_columns=None):
    rows = normalize_rows(rows)
    columns = []
    for row in rows:
        for col in row:
            if col not in columns:
                columns.append(col)
    key_columns = key_columns or _infer_key_columns(columns)

    column_profiles = [profile_column(col, rows).as_dict() for col in columns]
    by_kind = Counter(col["kind"] for col in column_profiles)
    duplicate_key_count = 0
    if key_columns:
        keys = [tuple(row.get(col) for col in key_columns) for row in rows]
        complete_keys = [key for key in keys if all(v is not None for v in key)]
        duplicate_key_count = len(complete_keys) - len(set(complete_keys))

    quality_flags = []
    for col in column_profiles:
        if col["null_rate"] > 0.2:
            quality_flags.append(f"sparse_column:{col['name']}:{col['null_rate']:.1%}_null")
        if col["kind"] == "metric" and col["stats"].get("negative_count", 0) and not any(
            token in col["name"].lower() for token in ("net", "pct", "change")
        ):
            quality_flags.append(f"negative_metric:{col['name']}")
    if duplicate_key_count:
        quality_flags.append(f"duplicate_key:{','.join(key_columns)}:{duplicate_key_count}")

    return {
        "table": table,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns_by_kind": dict(sorted(by_kind.items())),
        "key_columns": key_columns,
        "duplicate_key_count": duplicate_key_count,
        "quality_flags": quality_flags,
        "columns": column_profiles,
    }


def parse_table_name(name, default_schema):
    if "." in name:
        schema, table = name.split(".", 1)
    else:
        schema, table = default_schema, name
    return schema, table


def fetch_rows(table_name, limit=5000, schema=None):
    _, ds = get_active_datasource()
    default_schema = schema or ds["schemas"][0]
    schema, table = parse_table_name(table_name, default_schema)
    dialect = get_dialect(ds["engine"])
    fq = dialect.fq_table(schema, table)
    sql = f"SELECT * FROM {fq} LIMIT {int(limit)}"
    with get_engine(schema).connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return rows, f"{schema}.{table}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", help="table name, optionally schema-qualified")
    ap.add_argument("--rows-json", help="profile a JSON array instead of querying a database")
    ap.add_argument("--schema", default=None)
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--key", action="append", help="key column; may be repeated")
    args = ap.parse_args()

    if args.rows_json:
        rows = json.loads(args.rows_json)
        table = args.table
    elif args.table:
        rows, table = fetch_rows(args.table, limit=args.limit, schema=args.schema)
    else:
        raise SystemExit("provide --table or --rows-json")

    report = profile_rows(rows, table=table, key_columns=args.key)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
