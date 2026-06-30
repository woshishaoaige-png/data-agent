"""
Small read-only smoke checks for data-agent.

This is not the full 25-question eval. It verifies the high-risk mechanics that
the skill depends on: v_kline, catalog gates, units, latest dates, and empty or
sparse tables.
"""

import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))
from db import get_engine  # noqa: E402

CATALOG = Path(__file__).resolve().parents[1] / "catalog.json"


def catalog_table(catalog, schema, table):
    return catalog["schemas"][schema][table]


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    checks = []

    with get_engine().connect() as conn:
        conn.execute(text("SET SESSION max_execution_time=15000"))
        v_info = catalog_table(catalog, "Stock", "v_kline")
        checks.append(("v_kline_present_and_agent_facing", not v_info.get("internal") and v_info["type"] == "VIEW"))
        checks.append(("physical_kline_shards_are_internal", all(
            info.get("internal") and info.get("do_not_query")
            for name, info in catalog["schemas"]["Stock"].items()
            if name.startswith("kline_")
        )))

        latest_k = v_info["date_max"]
        latest_row = conn.execute(
            text("SELECT 1 FROM Stock.v_kline WHERE `date` = :d LIMIT 1"),
            {"d": latest_k},
        ).fetchone()
        checks.append(("latest_kline_has_row", bool(latest_row and latest_k)))

        holder = catalog_table(catalog, "Stock", "holder_number_snapshot")
        checks.append(("holder_number_blocks_market_rank", holder["coverage"] == "SINGLE_STOCK"))

        board = catalog_table(catalog, "Stock", "stock_board_data")
        checks.append(("stock_board_data_short_history", "SHORT_HISTORY" in board["flags"]))

        stock_flow = catalog_table(catalog, "Stock", "stock_moneyflow_snapshot")
        hsgt = catalog_table(catalog, "Stock", "hsgt_moneyflow_snapshot")
        dc = catalog_table(catalog, "Stock", "dc_moneyflow_snapshot")
        checks.append(("unit_stock_flow_wanyuan", stock_flow.get("unit") == "万元"))
        checks.append(("unit_hsgt_wanyuan", hsgt.get("unit") == "万元"))
        checks.append(("unit_dc_yuan", dc.get("unit") == "元"))
        checks.append(("stock_flow_stale_current", "STALE_CURRENT" in stock_flow["flags"]))

        stock_flow_view = catalog_table(catalog, "Stock", "v_stock_moneyflow_yi")
        board_dc_view = catalog_table(catalog, "Stock", "v_board_moneyflow_dc_yi")
        top_inst_view = catalog_table(catalog, "Stock", "v_top_inst_net_yi")
        checks.append(("semantic_stock_flow_unit_yi", stock_flow_view.get("unit") == "亿元"))
        checks.append(("semantic_board_dc_unit_yi", board_dc_view.get("unit") == "亿元"))
        checks.append(("semantic_top_inst_unit_yi", top_inst_view.get("unit") == "亿元"))

        daily = catalog_table(catalog, "Stock", "daily_selection_results")
        checks.append(("daily_selection_uses_date_col", daily.get("date_col") == "date"))

        pool = catalog_table(catalog, "Stock", "stock_pool_base")
        checks.append(("stock_pool_freshness_uses_update_date", pool.get("freshness_col") == "update_date"))

        tmp_count = conn.execute(text("SELECT COUNT(*) FROM Stock.tmp_pool_mv")).scalar()
        tmp = catalog_table(catalog, "Stock", "tmp_pool_mv")
        checks.append(("tmp_pool_mv_empty_tiny", int(tmp_count) == 0 and tmp["coverage"] == "TINY"))

        sentiment = catalog_table(catalog, "finance", "sentiment_index")
        checks.append(("sentiment_is_tiny_cross_schema", sentiment["coverage"] == "TINY"))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    if failed:
        raise SystemExit(f"smoke eval failed: {failed}")


if __name__ == "__main__":
    main()
