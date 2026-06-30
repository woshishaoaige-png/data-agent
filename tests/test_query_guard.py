import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from query_guard import guard_sql  # noqa: E402


def test_corr_requires_sample_count():
    result = guard_sql(
        "SELECT CORR(k.pctChg, f.main_net_yi) AS corr_pct_main_flow "
        "FROM Stock.v_kline k JOIN Stock.v_stock_moneyflow_yi f "
        "ON k.code=f.code AND k.date=f.trade_date "
        "WHERE k.pctChg IS NOT NULL AND f.main_net_yi IS NOT NULL",
        "过去60个交易日个股涨跌幅和主力净流入相关性",
    )
    assert result.status == "BLOCK"
    assert any("missing_stat_sample_check" in e for e in result.errors)


def test_corr_blocks_or_non_null_filter():
    result = guard_sql(
        "SELECT COUNT(*) AS n, CORR(k.pctChg, f.main_net_yi) AS corr_pct_main_flow "
        "FROM Stock.v_kline k JOIN Stock.v_stock_moneyflow_yi f "
        "ON k.code=f.code AND k.date=f.trade_date "
        "WHERE k.pctChg IS NOT NULL OR f.main_net_yi IS NOT NULL",
        "计算涨跌幅和主力资金相关性，并给样本数",
    )
    assert result.status == "BLOCK"
    assert any("pairwise_non_null_filter" in e for e in result.errors)


def test_aggregate_window_requires_rows_frame():
    result = guard_sql(
        "WITH rolled AS ("
        "SELECT trade_date, ts_code, AVG(main_net_yi) OVER "
        "(PARTITION BY ts_code ORDER BY trade_date) AS main_net_ma5 "
        "FROM Stock.v_stock_moneyflow_yi) "
        "SELECT * FROM rolled ORDER BY main_net_ma5 DESC LIMIT 10",
        "计算每只股票近5日主力净流入滚动均值",
    )
    assert result.status == "BLOCK"
    assert any("window_missing_rows_frame" in e for e in result.errors)


def test_rank_window_without_frame_allowed():
    result = guard_sql(
        "WITH latest_date AS (SELECT MAX(date) AS d FROM Stock.v_kline), "
        "ranked AS (SELECT k.date, k.code, k.pctChg, "
        "ROW_NUMBER() OVER (ORDER BY k.pctChg DESC) AS rn "
        "FROM Stock.v_kline k JOIN latest_date ld ON k.date = ld.d) "
        "SELECT * FROM ranked WHERE rn <= 10",
        "今天全市场涨幅最高10只股票，使用排名窗口",
    )
    assert result.status != "BLOCK"


def test_ad_hoc_regression_formula_blocks():
    result = guard_sql(
        "SELECT (COUNT(*) * SUM(x * y) - SUM(x) * SUM(y)) / "
        "NULLIF(COUNT(*) * SUM(x * x) - SUM(x) * SUM(x), 0) AS slope "
        "FROM Stock.v_kline",
        "回归主力净流入对涨跌幅的解释力",
    )
    assert result.status == "BLOCK"
    assert any("ad_hoc_regression_formula" in e for e in result.errors)
    assert any("pairwise_non_null_filter" in e for e in result.errors)


def test_covariance_requires_sample_count():
    result = guard_sql(
        "SELECT COVAR_SAMP(k.pctChg, f.main_net_yi) AS covariance "
        "FROM Stock.v_kline k JOIN Stock.v_stock_moneyflow_yi f "
        "ON k.code=f.code AND k.date=f.trade_date "
        "WHERE k.pctChg IS NOT NULL AND f.main_net_yi IS NOT NULL",
        "计算涨跌幅和主力资金协方差",
    )
    assert result.status == "BLOCK"
    assert any("missing_stat_sample_check" in e for e in result.errors)


def test_parenthesized_or_non_null_filter_blocks():
    result = guard_sql(
        "SELECT COUNT(*) AS n, CORR(k.pctChg, f.main_net_yi) AS corr_pct_main_flow "
        "FROM Stock.v_kline k JOIN Stock.v_stock_moneyflow_yi f "
        "ON k.code=f.code AND k.date=f.trade_date "
        "WHERE (k.pctChg IS NOT NULL) OR (f.main_net_yi IS NOT NULL)",
        "计算涨跌幅和主力资金相关性",
    )
    assert result.status == "BLOCK"
    assert any("pairwise_non_null_filter" in e for e in result.errors)


def test_named_aggregate_window_requires_rows_frame():
    result = guard_sql(
        "SELECT date, code, AVG(close) OVER w AS ma20 "
        "FROM Stock.v_kline WINDOW w AS (PARTITION BY code ORDER BY date)",
        "平安银行最近20日均线",
    )
    assert result.status == "BLOCK"
    assert any("window_missing_rows_frame" in e for e in result.errors)


def test_window_comment_does_not_spoof_rows_frame():
    result = guard_sql(
        "SELECT trade_date, ts_code, SUM(main_net_yi) OVER "
        "(PARTITION BY ts_code ORDER BY trade_date /* rows frame missing */) AS cum_net "
        "FROM Stock.v_stock_moneyflow_yi",
        "累计主力净流入",
    )
    assert result.status == "BLOCK"
    assert any("window_missing_rows_frame" in e for e in result.errors)


def test_cte_column_list_not_unknown_table():
    result = guard_sql(
        "WITH base(trade_date, code, close) AS ("
        "SELECT date, code, close FROM Stock.v_kline WHERE code='000001'), "
        "rolled AS (SELECT trade_date, code, AVG(close) OVER ("
        "PARTITION BY code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW"
        ") AS ma20, COUNT(close) OVER ("
        "PARTITION BY code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW"
        ") AS window_n FROM base) SELECT * FROM rolled WHERE window_n >= 20",
        "平安银行最近20个完整窗口的20日均线",
    )
    assert not any("unknown_table:Stock.base" in e for e in result.errors)


def test_latest_rank_between_blocks_cross_date_ranking():
    result = guard_sql(
        "WITH ranked AS (SELECT date, code, pctChg, "
        "ROW_NUMBER() OVER (ORDER BY pctChg DESC) AS rn FROM Stock.v_kline "
        "WHERE date BETWEEN DATE_SUB((SELECT MAX(date) FROM Stock.v_kline), INTERVAL 20 DAY) "
        "AND (SELECT MAX(date) FROM Stock.v_kline)) SELECT * FROM ranked WHERE rn <= 10",
        "今天全市场涨幅最高10只股票",
    )
    assert result.status == "BLOCK"
    assert any("cross_date_ranking" in e for e in result.errors)
