"""
catalog.json 自省生成器（阶段 0 / G2 + G3）

这是 data-agent 的【真相源】：直接从 MySQL information_schema 读取，
替代会漂移的 Obsidian 笔记。每次加表 / 改表后重跑即可，永不过时。

为每张表自动计算：
  - 列结构、主键、表/视图类型、精确行数
  - typed dimensions + distinct entity counts
  - 日期维度列 / freshness 列 + 时间跨度（min/max）
  - coverage 档位（G3 稀疏熔断的数据来源）：
        SINGLE_STOCK : 只有 1 只股票（如 holder_number 只有茅台）
        TINY         : 行数 < 100（如 dc_moneyflow_mkt 仅 6 行）
        OK           : 其余
      —— Agent 对非 OK 的表做"跨股票/排名/时序"查询时必须先熔断声明。

用法：
    python tools/gen_catalog.py            # 生成到 catalog.json
    python tools/gen_catalog.py --print    # 同时打印摘要
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).parent))
from db import get_engine  # noqa: E402
from config import get_active_datasource  # noqa: E402
from dialects import get_dialect  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[1] / "catalog.json"

# 股票维度列识别（自动兜底；特殊表用 DIMENSION_OVERRIDES）
STOCK_COLS = ["ts_code", "code", "symbol", "stock_code", "con_code"]
# 日期列：优先按 COLUMN_TYPE 识别真日期；周期型字符/整型列作兜底
DATE_TYPE_PREFIXES = ("date", "datetime", "timestamp")
PERIOD_COLS = ["rank_year", "month", "quarter"]

TINY_ROW_THRESHOLD = 100
SHORT_HISTORY_DAYS = 3          # distinct 日期 < 此值 → 时序不可靠
STALE_DAYS = 2                  # 真日期最新数据距今 > 此值 → 不可当成今日/当前

INTERNAL_TABLE_PREFIXES = ("kline_",)

# 表级维度覆盖：避免把板块 ts_code 误识别为股票代码。
DIMENSION_OVERRIDES = {
    "dc_moneyflow_snapshot": {"board_col": "ts_code"},
    "ths_daily_snapshot": {"board_col": "ts_code"},
    "ths_moneyflow_snapshot": {"board_col": "ts_code"},
    "ths_board_member": {"board_col": "ts_code", "stock_col": "con_code"},
    "stock_board_data": {"stock_col": "stock_code"},
    "v_kline": {"stock_col": "code"},
    "v_stock_moneyflow_yi": {"stock_col": "code"},
    "v_board_moneyflow_dc_yi": {"board_col": "ts_code"},
    "v_board_moneyflow_ths_yi": {"board_col": "ts_code"},
    "v_top_inst_net_yi": {"stock_col": "code"},
    "v_strategy_selection_latest": {"stock_col": "code"},
}

# 日期 / 新鲜度覆盖：date_col 描述业务事件，freshness_col 判断本地数据是否新。
DATE_OVERRIDES = {
    "daily_selection_results": {"date_col": "date", "is_real_date": True},
    "stock_pool_base": {
        "date_col": "list_date",
        "is_real_date": True,
        "freshness_col": "update_date",
    },
}

# 金额单位映射（业务知识，无法自省，集中维护在此一处；加资金表务必同步更新）
# 单位混淆是最危险的坑：万元 vs 元 差 1 万倍。stock_moneyflow 单位经实测确认为万元。
UNIT_MAP = {
    "hsgt_moneyflow_snapshot": "万元",
    "stock_moneyflow_snapshot": "万元",
    "dc_moneyflow_snapshot": "元",
    "dc_moneyflow_mkt_snapshot": "元",
    "ths_moneyflow_snapshot": "元",
    "margin_summary_snapshot": "元",
    "margin_detail_snapshot": "元",
    "top_list_snapshot": "元",
    "hsgt_top10_snapshot": "元",
    "v_stock_moneyflow_yi": "亿元",
    "v_board_moneyflow_dc_yi": "亿元",
    "v_board_moneyflow_ths_yi": "亿元",
    "v_top_inst_net_yi": "亿元",
}

UNIT_SOURCE = {
    "hsgt_moneyflow_snapshot": "Tushare moneyflow_hsgt; value scale sampled",
    "stock_moneyflow_snapshot": "Tushare moneyflow; value scale sampled",
    "dc_moneyflow_snapshot": "Eastmoney board moneyflow collector; value scale sampled",
    "dc_moneyflow_mkt_snapshot": "Eastmoney market moneyflow collector; value scale sampled",
    "ths_moneyflow_snapshot": "Tushare ths_moneyflow collector; value scale sampled",
    "margin_summary_snapshot": "Tushare margin summary collector; amount fields",
    "margin_detail_snapshot": "Tushare margin detail collector; amount fields",
    "top_list_snapshot": "Tushare top_list collector; amount fields",
    "hsgt_top10_snapshot": "Tushare hsgt_top10 collector; amount fields",
    "v_stock_moneyflow_yi": "semantic view normalized from stock_moneyflow_snapshot",
    "v_board_moneyflow_dc_yi": "semantic view normalized from dc_moneyflow_snapshot",
    "v_board_moneyflow_ths_yi": "semantic view normalized from ths_moneyflow_snapshot",
    "v_top_inst_net_yi": "semantic view normalized from top_inst_snapshot",
}


def _first_present(candidates, columns):
    cols_lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    return None


def _pick_date_col(columns):
    """返回 (列名, is_real_date)。优先真日期类型列，再退到周期型列。"""
    for c in columns:
        if c["type"].lower().startswith(DATE_TYPE_PREFIXES):
            return c["name"], True
    name = _first_present(PERIOD_COLS, [c["name"] for c in columns])
    return (name, False) if name else (None, False)


def _is_internal_table(table):
    return any(table.startswith(prefix) for prefix in INTERNAL_TABLE_PREFIXES)


def _distinct_count(conn, dialect, schema, table, col):
    fq = dialect.fq_table(schema, table)
    q = f"SELECT COUNT(DISTINCT {dialect.quote_ident(col)}) FROM {fq}"
    return conn.execute(text(q)).scalar()


def _date_bounds(conn, dialect, schema, table, col):
    fq = dialect.fq_table(schema, table)
    qc = dialect.quote_ident(col)
    q = f"SELECT MIN({qc}), MAX({qc}) FROM {fq}"
    return conn.execute(text(q)).fetchone()


def _freshness_days(conn, dialect, schema, table, col):
    fq = dialect.fq_table(schema, table)
    q = f"SELECT {dialect.datediff_today_sql(col)} FROM {fq}"
    return conn.execute(text(q)).scalar()


def introspect_table(conn, inspector, dialect, schema, table, table_type):
    # 列 + 主键（SQLAlchemy 反射，跨方言统一）
    raw_cols = inspector.get_columns(table, schema=schema)
    columns = [{"name": c["name"], "type": str(c["type"]), "key": ""} for c in raw_cols]
    col_names = [c["name"] for c in columns]
    try:
        pk = inspector.get_pk_constraint(table, schema=schema)
        primary_key = pk.get("constrained_columns", []) or []
    except Exception:
        primary_key = []
    for c in columns:
        if c["name"] in primary_key:
            c["key"] = "PRI"

    fq = dialect.fq_table(schema, table)
    row_count = conn.execute(text(f"SELECT COUNT(*) FROM {fq}")).scalar()

    info = {
        "type": table_type,
        "row_count": int(row_count),
        "primary_key": primary_key,
        "columns": columns,
    }
    if _is_internal_table(table):
        info["internal"] = True
        info["do_not_query"] = True

    dimensions = DIMENSION_OVERRIDES.get(table, {}).copy()
    if "stock_col" not in dimensions and "board_col" not in dimensions:
        stock_col = _first_present(STOCK_COLS, col_names)
        if stock_col:
            dimensions["stock_col"] = stock_col

    distinct_stocks = None
    if dimensions and row_count:
        info["dimensions"] = {}
    for dim_name, dim_col in dimensions.items():
        if dim_col not in col_names or not row_count:
            continue
        count_key = "distinct_" + dim_name.removesuffix("_col") + "s"
        distinct_entities = _distinct_count(conn, dialect, schema, table, dim_col)
        info["dimensions"][dim_name] = dim_col
        info[count_key] = int(distinct_entities)
        if dim_name == "stock_col":
            distinct_stocks = distinct_entities
            info["stock_col"] = dim_col
            info["distinct_stocks"] = int(distinct_stocks)
        elif dim_name == "board_col":
            info["board_col"] = dim_col
            info["distinct_boards"] = int(distinct_entities)

    date_override = DATE_OVERRIDES.get(table)
    if date_override:
        date_col = date_override["date_col"]
        is_real_date = date_override.get("is_real_date", False)
        freshness_col = date_override.get("freshness_col", date_col)
    else:
        date_col, is_real_date = _pick_date_col(columns)
        freshness_col = date_col

    distinct_dates = None
    freshness_days = None
    if date_col and row_count:
        info["date_col"] = date_col
        dmin, dmax = _date_bounds(conn, dialect, schema, table, date_col)
        info["date_min"] = str(dmin)
        info["date_max"] = str(dmax)
        distinct_dates = _distinct_count(conn, dialect, schema, table, date_col)
        info["distinct_dates"] = int(distinct_dates)
    if freshness_col and row_count and freshness_col in col_names and is_real_date:
        if freshness_col != date_col:
            info["freshness_col"] = freshness_col
            fmin, fmax = _date_bounds(conn, dialect, schema, table, freshness_col)
            info["freshness_min"] = str(fmin)
            info["freshness_max"] = str(fmax)
        freshness_days = _freshness_days(conn, dialect, schema, table, freshness_col)
        if freshness_days is not None:
            info["freshness_days"] = int(freshness_days)

    if table in UNIT_MAP:
        info["unit"] = UNIT_MAP[table]
        info["unit_source"] = UNIT_SOURCE.get(table, "manual mapping")

    if distinct_stocks == 1:
        info["coverage"] = "SINGLE_STOCK"
    elif row_count < TINY_ROW_THRESHOLD:
        info["coverage"] = "TINY"
    else:
        info["coverage"] = "OK"

    flags = []
    if distinct_dates is not None and distinct_dates < SHORT_HISTORY_DAYS:
        flags.append("SHORT_HISTORY")
    if freshness_days is not None and freshness_days > STALE_DAYS:
        flags.append("STALE_CURRENT")
    info["flags"] = flags

    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="do_print")
    args = ap.parse_args()

    catalog = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "information_schema introspection (tools/gen_catalog.py)",
        "coverage_legend": {
            "SINGLE_STOCK": "仅 1 只股票，禁止用于跨股票对比/排名/横截面",
            "TINY": "行数 < 100，时序/趋势结论不可靠，须披露样本量",
            "OK": "横截面可正常查询（仍需看 flags 判断时序能力）",
        },
        "flags_legend": {
            "SHORT_HISTORY": "不同日期 < 3，禁止做趋势/时序/「过去N月」类查询",
            "STALE_CURRENT": "真日期/新鲜度列距今 > 2 天，勿当今日/当前结果",
        },
        "schemas": {},
    }

    _, ds = get_active_datasource()
    schemas = ds["schemas"]
    dialect = get_dialect(ds["engine"])

    engine = get_engine()
    inspector = inspect(engine)
    with engine.connect() as conn:
        for schema in schemas:
            table_names = inspector.get_table_names(schema=schema)
            view_names = inspector.get_view_names(schema=schema)
            schema_entry = {}
            for table_name in sorted(table_names):
                schema_entry[table_name] = introspect_table(
                    conn, inspector, dialect, schema, table_name, "BASE TABLE"
                )
            for view_name in sorted(view_names):
                schema_entry[view_name] = introspect_table(
                    conn, inspector, dialect, schema, view_name, "VIEW"
                )
            catalog["schemas"][schema] = schema_entry

    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ catalog 已生成: {OUTPUT}")

    # 始终打印 coverage 摘要（熔断的关键）
    print("\n=== coverage 摘要 ===")
    for schema, tables in catalog["schemas"].items():
        for tname, info in tables.items():
            cov = info["coverage"]
            tags = info.get("flags", [])
            if cov != "OK" or tags or args.do_print:
                marks = ([] if cov == "OK" else [cov]) + tags
                mark_str = f"  ⚠️ {'+'.join(marks)}" if marks else ""
                ds = info.get("distinct_stocks")
                ds_str = f", {ds}只" if ds is not None else ""
                dd = info.get("distinct_dates")
                dd_str = f", {dd}天" if dd is not None else ""
                print(f"  {schema}.{tname}: {info['row_count']}行{ds_str}{dd_str}{mark_str}")


if __name__ == "__main__":
    main()
