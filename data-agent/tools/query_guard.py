"""
Static guardrail checks for data-agent SQL.

This is intentionally small: it does not try to be a full SQL parser. It catches
the known high-risk failure classes before a query is trusted.
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.json"
JOIN_POLICY = ROOT / "policies" / "join_policy.json"

FROM_JOIN_TOKEN_RE = re.compile(r"\b(?:from|join)\s+([`A-Za-z_][`.\w]*)", re.IGNORECASE)
CTE_NAME_RE = re.compile(r"(?:\bwith|,)\s+([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s+as\s*\(", re.IGNORECASE)
MONEY_RE = re.compile(r"(amount|money|net_|buy_|sell_|rzye|rzmre|rqye|rzrqye)", re.IGNORECASE)
# 注意：不收录"最近"——它既指"最新一次"(列表)又指"一段时间"(趋势)，歧义太大，
# 会把 *_latest 快照的列表查询误判为趋势。真趋势由下列更明确的词兜住。
TREND_RE = re.compile(r"(trend|趋势|走势|过去|半年|三个月|一个月|变化|持续)", re.IGNORECASE)
RANK_RE = re.compile(r"(top|rank|排名|最高|最低|最多|最少|占比|分布|全市场)", re.IGNORECASE)
LATEST_RE = re.compile(r"(today|current|latest|今天|当前|最新|今日)", re.IGNORECASE)
STAT_RE = re.compile(
    r"\b(corr|correlation|covar_samp|covar_pop|variance|var_samp|var_pop|"
    r"regr_slope|regr_intercept|regr_r2|regr_count|stddev|stddev_samp|stddev_pop)\s*\(",
    re.IGNORECASE,
)
CORR_RE = re.compile(r"\bcorr\s*\(", re.IGNORECASE)
PAIRWISE_STAT_RE = re.compile(r"\b(corr|covar_samp|covar_pop|regr_(slope|intercept|r2|count))\s*\(", re.IGNORECASE)
REGR_RE = re.compile(r"\bregr_(slope|intercept|r2|count)\s*\(", re.IGNORECASE)
AD_HOC_REGR_RE = re.compile(r"count\s*\(\s*\*\s*\)\s*\*\s*sum\s*\([^)]*\*[^)]*\)\s*-\s*sum\s*\([^)]*\)\s*\*\s*sum\s*\(", re.IGNORECASE)
STDDEV_POP_RE = re.compile(r"\bstddev_pop\s*\(", re.IGNORECASE)
STAT_SAMPLE_RE = re.compile(r"\b(count\s*\(|\bn\s+|as\s+n\b|pairwise_non_null_n|regr_count|window_n)", re.IGNORECASE)
PAIRWISE_AND_RE = re.compile(r"\b\w+(?:\.\w+)?\s+is\s+not\s+null\s+and\s+\w+(?:\.\w+)?\s+is\s+not\s+null\b", re.IGNORECASE)
PAIRWISE_NOT_NULL_TOKEN_RE = re.compile(r"\b\w+(?:\.\w+)?\s+is\s+not\s+null\b", re.IGNORECASE)
NULL_OR_NULL_RE = re.compile(r"is\s+not\s+null\s*\)?\s+or\s+\(?\s*\w+(?:\.\w+)?\s+is\s+not\s+null", re.IGNORECASE)
DEMORGAN_NOT_NULL_RE = re.compile(r"not\s*\([^)]*\bis\s+null\b[^)]*\bor\b[^)]*\bis\s+null\b[^)]*\)", re.IGNORECASE)
SAMPLE_VOL_RE = re.compile(r"(sample|样本|波动|volatility|stddev|标准差)", re.IGNORECASE)
ROLLING_RE = re.compile(r"(rolling|moving|滚动|移动|均线|近\d+日|最近\d+日)", re.IGNORECASE)
DAILY_RANK_RE = re.compile(r"(每天|每日|逐日|daily)", re.IGNORECASE)
AGG_WINDOW_RE = re.compile(
    r"\b(sum|avg|min|max|count|stddev(?:_samp|_pop)?|corr)\s*\((?:[^()]|\([^()]*\))*\)\s+over\s*\(([^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)
NAMED_AGG_WINDOW_RE = re.compile(
    r"\b(sum|avg|min|max|count|stddev(?:_samp|_pop)?|corr)\s*\((?:[^()]|\([^()]*\))*\)\s+over\s+([A-Za-z_]\w*)\b",
    re.IGNORECASE | re.DOTALL,
)
RANK_WINDOW_RE = re.compile(
    r"\b(row_number|rank|dense_rank|ntile)\s*\([^)]*\)\s+over\s*\(([^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)
WINDOW_REF_RE = re.compile(r"\bover\s+[A-Za-z_]\w*\b", re.IGNORECASE)
WINDOW_DEF_RE = re.compile(r"\bwindow\s+[A-Za-z_]\w*\s+as\s*\(([^)]*)\)", re.IGNORECASE | re.DOTALL)


@dataclass
class GuardResult:
    status: str = "PASS"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)

    def add_error(self, message):
        self.errors.append(message)
        self.status = "BLOCK"

    def add_warning(self, message):
        self.warnings.append(message)
        if self.status == "PASS":
            self.status = "WARN"


def load_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def load_policy():
    return json.loads(JOIN_POLICY.read_text(encoding="utf-8"))


def strip_sql_comments(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def normalize_table(schema, table):
    return f"{schema}.{table}"


def extract_tables(sql):
    cte_names = {name.lower() for name in CTE_NAME_RE.findall(sql)}
    found = []
    for token in FROM_JOIN_TOKEN_RE.findall(sql):
        token = token.strip("`").replace("`", "")
        if "." in token:
            schema, table = token.split(".", 1)
            found.append(normalize_table(schema, table))
        elif token.lower() not in {"select", "where", "on", "using"} and token.lower() not in cte_names:
            found.append(normalize_table("Stock", token))
    return sorted(set(found))


def catalog_info(catalog, fq):
    schema, table = fq.split(".", 1)
    return catalog.get("schemas", {}).get(schema, {}).get(table)


def has_pair(tables, left, right):
    return left in tables and right in tables


def pair_allowed(policy, left, right):
    for item in policy.get("allowed", []):
        pair = {item["left"], item["right"]}
        if {left, right} == pair:
            return item
    return None


def check_forbidden_pairs(policy, tables, result):
    for rule in policy.get("forbidden", []):
        left_re = re.compile(rule["left_pattern"])
        right_re = re.compile(rule["right_pattern"])
        for left in tables:
            for right in tables:
                if left == right:
                    continue
                if left_re.search(left) and right_re.search(right):
                    result.add_error(f"forbidden_join:{rule['name']}: {rule['reason']}")


def check_unapproved_joins(policy, tables, result):
    if len(tables) < 2:
        return
    # Only enforce on known high-risk families for now.
    high_risk = [t for t in tables if any(x in t for x in [
        "dc_moneyflow", "ths_", "sentiment_index", "stock_moneyflow",
        "margin_detail", "top_", "v_kline", "stock_board_data"
    ])]
    for i, left in enumerate(high_risk):
        for right in high_risk[i + 1:]:
            if pair_allowed(policy, left, right):
                continue
            # Board source mixes and sentiment joins are handled as errors above.
            if "sentiment_index" in left or "sentiment_index" in right:
                continue
            if ("dc_moneyflow" in left and "ths_" in right) or ("dc_moneyflow" in right and "ths_" in left):
                continue
            # Warn, not block, to allow exploratory single-query combinations.
            result.add_warning(f"unregistered_join:{left}<->{right}: verify join keys and date overlap")


def check_statistical_sql(sql, text, tables, catalog, result):
    stat_like = STAT_RE.search(sql) or AD_HOC_REGR_RE.search(sql)
    if not stat_like:
        return

    if AD_HOC_REGR_RE.search(sql):
        result.add_error("ad_hoc_regression_formula: use dialect regression helpers and expose self-check columns")

    if REGR_RE.search(sql) and not re.search(r"\b(count\s*\(|regr_count\s*\()", sql, re.IGNORECASE):
        result.add_error("missing_regr_self_check: regression SQL must expose sample count")
    elif not STAT_SAMPLE_RE.search(sql):
        result.add_error("missing_stat_sample_check: statistical SQL must expose sample size")

    has_pairwise_filter = (
        len(PAIRWISE_NOT_NULL_TOKEN_RE.findall(sql)) >= 2
        or DEMORGAN_NOT_NULL_RE.search(sql)
    )
    if (PAIRWISE_STAT_RE.search(sql) or AD_HOC_REGR_RE.search(sql)) and not has_pairwise_filter:
        result.add_error("pairwise_non_null_filter: correlation/regression must filter pairwise non-null inputs")
    if NULL_OR_NULL_RE.search(sql):
        result.add_error("pairwise_non_null_filter: use AND, not OR, for pairwise non-null statistical inputs")

    units = {
        catalog_info(catalog, fq).get("unit")
        for fq in tables
        if catalog_info(catalog, fq) and catalog_info(catalog, fq).get("unit")
    }
    if len(units) > 1 and MONEY_RE.search(text) and not re.search(r"/\s*(10000|100000000)|_yi\b", sql, re.IGNORECASE):
        result.add_error("stat_unit_not_normalized: statistical money inputs must be normalized before use")

    if STDDEV_POP_RE.search(sql) and SAMPLE_VOL_RE.search(text):
        result.add_warning("stddev_sample_required: use sample standard deviation for sample volatility")

    if (
        re.search(r"\bgroup\s+by\b", sql, re.IGNORECASE)
        and re.search(r"\border\s+by\b[^;]*(corr|slope|r2|stddev)", sql, re.IGNORECASE)
        and not re.search(r"\bhaving\b[^;]*(n|count\s*\()[^;]*(>=|>)\s*(20|[3-9]\d+)", sql, re.IGNORECASE)
        and not re.search(r"\bwhere\b[^;]*\bn\b\s*(>=|>)\s*(20|[3-9]\d+)", sql, re.IGNORECASE)
    ):
        result.add_warning("missing_stat_sample_threshold: grouped statistical ranking should filter to a minimum sample")


def _has_window_def_with_rows(sql):
    return any(" rows " in f" {match.group(1).lower()} " for match in WINDOW_DEF_RE.finditer(sql))


def check_window_sql(sql, text, result):
    lowered = sql.lower()
    aggregate_windows = list(AGG_WINDOW_RE.finditer(sql))
    named_aggregate_windows = list(NAMED_AGG_WINDOW_RE.finditer(sql))
    rank_windows = list(RANK_WINDOW_RE.finditer(sql))

    for match in aggregate_windows:
        frame = match.group(2).lower()
        if "order by" in frame and " rows " not in f" {frame} ":
            result.add_error("window_missing_rows_frame: aggregate time-series windows must use an explicit ROWS frame")
            break

    if named_aggregate_windows and not _has_window_def_with_rows(sql):
        result.add_error("window_missing_rows_frame: named aggregate windows must define an explicit ROWS frame")

    has_rolling_aggregate = bool((aggregate_windows or named_aggregate_windows) and (ROLLING_RE.search(text) or " preceding " in lowered))
    if has_rolling_aggregate and not re.search(r"\bwindow_n\b", sql, re.IGNORECASE):
        result.add_error("rolling_window_missing_window_n: rolling windows must expose window_n")

    if (
        re.search(r"\bwith\b", sql, re.IGNORECASE)
        and re.search(r"\blimit\s+\d+", sql, re.IGNORECASE)
        and re.search(r"\b(group\s+by|avg\s*\(|sum\s*\(|count\s*\(|stddev|corr\s*\()", sql, re.IGNORECASE)
        and re.search(r"\blimit\s+\d+[\s\S]*\b(group\s+by|avg\s*\(|sum\s*\(|count\s*\(|stddev|corr\s*\()", sql, re.IGNORECASE)
    ):
        result.add_error("nested_limit_before_aggregation: do not LIMIT nested source rows before aggregation")

    if LATEST_RE.search(text) and rank_windows and re.search(r"\bdate\s*>=|\btrade_date\s*>=|\bdate\s+between\b|\btrade_date\s+between\b", sql, re.IGNORECASE):
        result.add_error("cross_date_ranking: latest TopN ranking must filter to the latest date before ranking")
    if (
        LATEST_RE.search(text)
        and RANK_RE.search(text)
        and re.search(r"\border\s+by\b[\s\S]*\blimit\s+\d+", sql, re.IGNORECASE)
        and re.search(r"\b(date|trade_date)\s*>=|\b(date|trade_date)\s+between\b", sql, re.IGNORECASE)
        and not re.search(r"\b(date|trade_date)\s*=\s*\(\s*select\s+max\s*\(", sql, re.IGNORECASE)
    ):
        result.add_error("cross_date_ranking: latest TopN must filter to the latest date before ORDER BY/LIMIT")

    for match in rank_windows:
        frame = match.group(2).lower()
        if "order by" not in frame:
            result.add_error("window_missing_order_by: ranking windows must include ORDER BY")
        if DAILY_RANK_RE.search(text) and "partition by" not in frame:
            result.add_error("window_missing_partition_by_date: daily rankings must partition by date")

    if (
        ROLLING_RE.search(text)
        and re.search(r"\bcode\s+in\s*\(", sql, re.IGNORECASE)
        and aggregate_windows
        and not any("partition by" in match.group(2).lower() for match in aggregate_windows)
    ):
        result.add_error("window_missing_partition_by_entity: entity rolling windows must partition by entity")


def guard_sql(sql, intent=""):
    catalog = load_catalog()
    policy = load_policy()
    result = GuardResult()
    clean_sql = strip_sql_comments(sql)
    tables = extract_tables(clean_sql)
    result.tables = tables
    text = f"{intent}\n{clean_sql}"

    for fq in tables:
        info = catalog_info(catalog, fq)
        if not info:
            result.add_error(f"unknown_table:{fq}")
            continue
        table = fq.split(".", 1)[1]
        if info.get("do_not_query") or table.startswith("kline_"):
            result.add_error(f"do_not_query:{fq}: use Stock.v_kline")
        coverage = info.get("coverage")
        flags = info.get("flags", [])
        if coverage == "SINGLE_STOCK" and RANK_RE.search(text):
            result.add_error(f"single_stock_misuse:{fq}: cannot support ranking/distribution/breadth")
        if coverage == "TINY":
            result.add_warning(f"tiny_source:{fq}: disclose row count and date range")
        if "SHORT_HISTORY" in flags and TREND_RE.search(text):
            result.add_error(f"short_history_trend:{fq}: cannot support trend/history claim")
        if "STALE_CURRENT" in flags and LATEST_RE.search(intent):
            result.add_warning(f"stale_current:{fq}: disclose local latest date")

    units = sorted({
        catalog_info(catalog, fq).get("unit")
        for fq in tables
        if catalog_info(catalog, fq) and catalog_info(catalog, fq).get("unit")
    })
    if len(units) > 1 and MONEY_RE.search(text):
        if not re.search(r"(亿元|normalize|normalized|unit|单位|归一)", text, re.IGNORECASE):
            result.add_error(f"unit_mismatch:{','.join(units)}: normalize money fields before comparing")

    check_forbidden_pairs(policy, tables, result)
    check_unapproved_joins(policy, tables, result)
    check_statistical_sql(clean_sql, text, tables, catalog, result)
    check_window_sql(clean_sql, text, result)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True)
    ap.add_argument("--intent", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = guard_sql(args.sql, args.intent)
    payload = {
        "status": result.status,
        "tables": result.tables,
        "errors": result.errors,
        "warnings": result.warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload)
    if result.status == "BLOCK":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
