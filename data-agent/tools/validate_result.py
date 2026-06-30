"""Validate query results before data-agent presents an answer.

QueryGuard catches known SQL risks before execution. This module checks the
shape and values returned by a query: empty results, duplicate grains, all-null
metrics, implausible percentages, and trend/ranking claims unsupported by the
actual result set.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from numbers import Number
from pathlib import Path
from statistics import mean

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))
from db import get_engine  # noqa: E402

TREND_RE = re.compile(r"(trend|趋势|走势|过去|半年|三个月|一个月|变化|持续|历史)", re.IGNORECASE)
RANK_RE = re.compile(r"(top\s*(\d+)|前\s*(\d+)|排名|最高|最低|最多|最少)", re.IGNORECASE)
LATEST_TOPN_RE = re.compile(r"(today|current|latest|今天|当前|最新|今日).*(top|前|最高|最低|最多|最少|排名)", re.IGNORECASE)
STAT_INTENT_RE = re.compile(r"(corr|correlation|相关|回归|regression|regr|stddev|标准差|波动|volatility)", re.IGNORECASE)
ROLLING_INTENT_RE = re.compile(r"(rolling|moving|滚动|移动|均线|近\d+日|最近\d+日)", re.IGNORECASE)
METRIC_RE = re.compile(
    r"(amount|money|net|buy|sell|price|close|open|high|low|pct|rate|ratio|余额|金额|占比)",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"(^pct|pct|percent|rate|ratio|占比|比例|涨幅|跌幅)", re.IGNORECASE)
DATE_COLS = {"date", "trade_date", "report_date", "selection_date", "month", "quarter", "rank_year"}
ID_COLS = {"code", "ts_code", "stock_code", "con_code", "symbol"}


@dataclass
class ValidationResult:
    status: str = "PASS"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add_error(self, message):
        self.errors.append(message)
        self.status = "BLOCK"

    def add_warning(self, message):
        self.warnings.append(message)
        if self.status == "PASS":
            self.status = "WARN"


def _normalize_rows(rows):
    normalized = []
    for row in rows:
        if hasattr(row, "_mapping"):
            normalized.append(dict(row._mapping))
        else:
            normalized.append(dict(row))
    return normalized


def _present_columns(rows, columns=None):
    if columns:
        return list(columns)
    if not rows:
        return []
    seen = []
    for row in rows:
        for col in row:
            if col not in seen:
                seen.append(col)
    return seen


def _non_null(values):
    return [v for v in values if v is not None]


def _looks_numeric(values):
    vals = _non_null(values)
    if not vals:
        return False
    return all(isinstance(v, Number) and not isinstance(v, bool) for v in vals)


def _numeric_value(value):
    if isinstance(value, Number) and not isinstance(value, bool):
        return float(value)
    return None


def _infer_grain(columns):
    cols = set(columns)
    if {"trade_date", "ts_code"}.issubset(cols):
        return ["trade_date", "ts_code"]
    if {"trade_date", "code"}.issubset(cols):
        return ["trade_date", "code"]
    if {"date", "code"}.issubset(cols):
        return ["date", "code"]
    if "ts_code" in cols:
        return ["ts_code"]
    if "code" in cols:
        return ["code"]
    return []


def _requested_top_n(text_value):
    match = RANK_RE.search(text_value)
    if not match:
        return None
    for group in match.groups():
        if group and group.isdigit():
            return int(group)
    return 10


def _first_numeric(row, names):
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name)
        numeric = _numeric_value(value)
        if numeric is not None:
            return numeric
    return None


def _metric_columns(columns):
    return [col for col in columns if METRIC_RE.search(col)]


def _has_stat_column(columns):
    return any(
        re.search(r"(corr|correlation|rho|pearson|r2|r_squared|rsq|r_sq|stddev|variance|var_|slope|intercept|regr)", col, re.IGNORECASE)
        for col in columns
    )


def validate_rows(rows, columns=None, intent="", sql=""):
    rows = _normalize_rows(rows)
    columns = _present_columns(rows, columns)
    result = ValidationResult(stats={"row_count": len(rows), "columns": columns})
    text_value = f"{intent}\n{sql}"

    if not rows:
        result.add_warning("empty_result: query returned zero rows; answer should say no matching rows")
        return result

    date_cols = [c for c in columns if c.lower() in DATE_COLS]
    for col in date_cols:
        values = _non_null([row.get(col) for row in rows])
        distinct = sorted({str(v) for v in values})
        result.stats[f"distinct_{col}"] = len(distinct)
        if distinct:
            result.stats[f"{col}_min"] = distinct[0]
            result.stats[f"{col}_max"] = distinct[-1]
        if TREND_RE.search(text_value) and len(distinct) < 3:
            result.add_error(f"insufficient_trend_points:{col}: only {len(distinct)} distinct periods")
        if LATEST_TOPN_RE.search(text_value) and len(distinct) > 1:
            result.add_error(f"cross_date_topn_multiple_dates:{col}: latest TopN result spans {len(distinct)} dates")

    grain = _infer_grain(columns)
    if grain:
        keys = [tuple(row.get(col) for col in grain) for row in rows]
        complete_keys = [key for key in keys if all(v is not None for v in key)]
        duplicates = len(complete_keys) - len(set(complete_keys))
        result.stats["grain"] = grain
        result.stats["duplicate_grain_rows"] = duplicates
        if duplicates:
            result.add_warning(
                f"duplicate_grain:{','.join(grain)}: {duplicates} duplicate rows; check join explosion or aggregation"
            )

    requested_n = _requested_top_n(text_value)
    if requested_n and len(rows) < requested_n:
        result.add_warning(f"short_topn_result: requested top {requested_n}, got {len(rows)} rows")

    stat_requested = bool(STAT_INTENT_RE.search(text_value) or _has_stat_column(columns))
    if stat_requested:
        for row in rows:
            sample_n = _first_numeric(row, ["pairwise_non_null_n", "regr_count", "n", "sample_n", "window_n"])
            total_n = _first_numeric(row, ["total_rows", "total_n", "rows"])
            if sample_n is None:
                result.add_warning("missing_stat_sample_check: statistical result should expose sample size")
            else:
                result.stats["stat_sample_min"] = min(result.stats.get("stat_sample_min", sample_n), sample_n)
                min_required = 3 if any("stddev" in col.lower() for col in columns) else 20
                if sample_n < min_required:
                    result.add_error(f"insufficient_stat_sample: n={sample_n:g}, required>={min_required}")
                if total_n and sample_n > 0 and sample_n / total_n < 0.5:
                    result.add_warning(
                        f"pairwise_non_null_shrinkage: statistical sample n={sample_n:g} from total={total_n:g}"
                    )

            for col, value in row.items():
                lname = str(col).lower()
                numeric = _numeric_value(value)
                if numeric is None:
                    continue
                if re.search(r"(corr|correlation|rho|pearson)", lname) and not -1 <= numeric <= 1:
                    result.add_error(f"corr_out_of_range:{col}: {numeric:g}")
                if lname in {"r2", "regr_r2", "r_squared", "rsq", "r_sq"} and not 0 <= numeric <= 1:
                    result.add_error(f"regr_r2_out_of_range:{col}: {numeric:g}")
                if "stddev" in lname and numeric < 0:
                    result.add_error(f"stddev_negative:{col}: {numeric:g}")

        metric_cols = _metric_columns(columns)
        if len(metric_cols) >= 2:
            pairwise_rows = [
                row for row in rows
                if sum(row.get(col) is not None for col in metric_cols[:2]) == 2
            ]
            if not pairwise_rows:
                result.add_error(
                    f"no_pairwise_non_null_rows:{','.join(metric_cols[:2])}: statistical inputs have no paired values"
                )

    if ROLLING_INTENT_RE.search(text_value):
        rolling_cols = [
            col for col in columns
            if re.search(r"(ma\d+|rolling|moving|avg|mean|sum|min|max|close|net|stddev|corr)", col, re.IGNORECASE)
        ]
        if rolling_cols and "window_n" not in {col.lower() for col in columns}:
            result.add_error("rolling_window_missing_window_n: rolling result must expose window_n")

    for col in columns:
        values = [row.get(col) for row in rows]
        non_null = _non_null(values)
        null_count = len(values) - len(non_null)
        result.stats[f"{col}_null_count"] = null_count
        if not non_null and METRIC_RE.search(col):
            result.add_warning(f"all_null_metric:{col}: metric column has no non-null values")
        if _looks_numeric(values):
            numeric = [float(v) for v in non_null]
            result.stats[f"{col}_min"] = min(numeric)
            result.stats[f"{col}_max"] = max(numeric)
            result.stats[f"{col}_avg"] = mean(numeric)
            if PERCENT_RE.search(col):
                extreme = [v for v in numeric if abs(v) > 100]
                # A-share pct_change can exceed 10/20 for special cases, but >100%
                # is almost certainly a scale or denominator error.
                if extreme:
                    result.add_warning(
                        f"percent_out_of_range:{col}: {len(extreme)} values outside [-100,100]"
                    )

    missing_ids = [
        col for col in columns
        if col.lower() in ID_COLS and any(row.get(col) is None for row in rows)
    ]
    for col in missing_ids:
        result.add_warning(f"null_identifier:{col}: identifier contains nulls")

    return result


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def payload(result):
    return {
        "status": result.status,
        "errors": result.errors,
        "warnings": result.warnings,
        "stats": result.stats,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", help="SQL to execute and validate")
    ap.add_argument("--intent", default="")
    ap.add_argument("--schema", default=None, help="schema/database for db.py connection")
    ap.add_argument("--rows-json", help="validate rows from a JSON array instead of executing SQL")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.sql and not args.rows_json:
        raise SystemExit("provide --sql or --rows-json")

    if args.rows_json:
        rows = json.loads(args.rows_json)
    else:
        with get_engine(args.schema).connect() as conn:
            rows = conn.execute(text(args.sql)).mappings().all()

    result = validate_rows(rows, intent=args.intent, sql=args.sql or "")
    data = payload(result)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default))
    else:
        print(data)
    if result.status == "BLOCK":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
