import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_result import validate_rows  # noqa: E402


def test_empty_result_warns():
    result = validate_rows([], intent="最新行业板块涨幅 Top5")
    assert result.status == "WARN"
    assert any("empty_result" in w for w in result.warnings)


def test_short_trend_blocks():
    rows = [
        {"trade_date": "2026-06-26", "net_yi": 1.2},
        {"trade_date": "2026-06-27", "net_yi": 1.3},
    ]
    result = validate_rows(rows, intent="最近半年趋势")
    assert result.status == "BLOCK"
    assert any("insufficient_trend_points" in e for e in result.errors)


def test_duplicate_grain_warns_join_explosion():
    rows = [
        {"trade_date": "2026-06-26", "ts_code": "000001.SZ", "net_yi": 1.0},
        {"trade_date": "2026-06-26", "ts_code": "000001.SZ", "net_yi": 2.0},
    ]
    result = validate_rows(rows)
    assert result.status == "WARN"
    assert result.stats["duplicate_grain_rows"] == 1


def test_percent_out_of_range_warns():
    rows = [{"code": "000001", "pct_change": 120.0}]
    result = validate_rows(rows)
    assert result.status == "WARN"
    assert any("percent_out_of_range" in w for w in result.warnings)


def test_all_null_metric_warns():
    rows = [{"code": "000001", "net_yi": None}]
    result = validate_rows(rows)
    assert result.status == "WARN"
    assert any("all_null_metric" in w for w in result.warnings)


def test_decimal_metrics_are_numeric():
    rows = [{"code": "000001", "net_yi": Decimal("1.25")}]
    result = validate_rows(rows)
    assert result.status == "PASS"
    assert result.stats["net_yi_max"] == 1.25


def test_corr_out_of_range_blocks():
    rows = [{"corr": 1.2, "pairwise_non_null_n": 45}]
    result = validate_rows(rows, intent="相关性结果校验")
    assert result.status == "BLOCK"
    assert any("corr_out_of_range" in e for e in result.errors)


def test_regr_r2_out_of_range_blocks():
    rows = [{"slope": 0.8, "regr_count": 42, "r2": 1.07}]
    result = validate_rows(rows, intent="回归结果校验")
    assert result.status == "BLOCK"
    assert any("regr_r2_out_of_range" in e for e in result.errors)


def test_stddev_negative_blocks():
    rows = [{"code": "000001", "stddev_pct": -2.3, "n": 60}]
    result = validate_rows(rows, intent="波动率结果校验")
    assert result.status == "BLOCK"
    assert any("stddev_negative" in e for e in result.errors)


def test_latest_topn_multiple_dates_blocks():
    rows = [
        {"date": "2026-06-26", "code": "000001", "pctChg": 10.02, "rn": 1},
        {"date": "2026-06-25", "code": "000002", "pctChg": 9.88, "rn": 2},
    ]
    result = validate_rows(rows, intent="今天全市场涨幅最高5只股票")
    assert result.status == "BLOCK"
    assert any("cross_date_topn_multiple_dates" in e for e in result.errors)


def test_rolling_result_requires_window_n():
    rows = [{"date": "2026-06-26", "code": "000001", "ma5": 12.31}]
    result = validate_rows(rows, intent="平安银行最近5日滚动均线")
    assert result.status == "BLOCK"
    assert any("rolling_window_missing_window_n" in e for e in result.errors)


def test_stat_aliases_are_range_checked():
    result = validate_rows([{"rho": 1.2, "r_squared": 1.1, "n": 45}], intent="相关和回归结果校验")
    assert result.status == "BLOCK"
    assert any("corr_out_of_range:rho" in e for e in result.errors)
    assert any("regr_r2_out_of_range:r_squared" in e for e in result.errors)


def test_rolling_avg_alias_requires_window_n():
    rows = [{"date": "2026-06-26", "code": "000001", "avg_close": 12.3}]
    result = validate_rows(rows, intent="平安银行最近5日平均收盘价")
    assert result.status == "BLOCK"
    assert any("rolling_window_missing_window_n" in e for e in result.errors)
