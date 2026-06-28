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
MONEY_RE = re.compile(r"(amount|money|net_|buy_|sell_|rzye|rzmre|rqye|rzrqye)", re.IGNORECASE)
# 注意：不收录"最近"——它既指"最新一次"(列表)又指"一段时间"(趋势)，歧义太大，
# 会把 *_latest 快照的列表查询误判为趋势。真趋势由下列更明确的词兜住。
TREND_RE = re.compile(r"(trend|趋势|走势|过去|半年|三个月|一个月|变化|持续)", re.IGNORECASE)
RANK_RE = re.compile(r"(top|rank|排名|最高|最低|最多|最少|占比|分布|全市场)", re.IGNORECASE)
LATEST_RE = re.compile(r"(today|current|latest|今天|当前|最新|今日)", re.IGNORECASE)


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


def normalize_table(schema, table):
    return f"{schema}.{table}"


def extract_tables(sql):
    found = []
    for token in FROM_JOIN_TOKEN_RE.findall(sql):
        token = token.strip("`").replace("`", "")
        if "." in token:
            schema, table = token.split(".", 1)
            found.append(normalize_table(schema, table))
        elif token.lower() not in {"select", "where", "on", "using"}:
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


def guard_sql(sql, intent=""):
    catalog = load_catalog()
    policy = load_policy()
    result = GuardResult()
    tables = extract_tables(sql)
    result.tables = tables
    text = f"{intent}\n{sql}"

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
        if "STALE_CURRENT" in flags and LATEST_RE.search(text):
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
