import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from dialects import get_dialect  # noqa: E402


def test_mysql_quote():
    assert get_dialect("mysql").quote_ident("Stock") == "`Stock`"


def test_pg_quote():
    assert get_dialect("postgresql").quote_ident("Stock") == '"Stock"'


def test_hive_quote():
    assert get_dialect("hive").quote_ident("t") == "`t`"


def test_mysql_datediff():
    assert get_dialect("mysql").datediff_today_sql("date") == \
        "DATEDIFF(CURDATE(), DATE(MAX(`date`)))"


def test_pg_datediff():
    assert get_dialect("postgresql").datediff_today_sql("d") == \
        'CURRENT_DATE - MAX("d")::date'


def test_hive_datediff():
    assert get_dialect("hive").datediff_today_sql("d") == \
        "datediff(current_date, max(`d`))"


def test_fq_table_mysql():
    assert get_dialect("mysql").fq_table("Stock", "v_kline") == "`Stock`.`v_kline`"


def test_fq_table_pg():
    assert get_dialect("postgresql").fq_table("public", "t") == '"public"."t"'


def test_statistical_functions_mysql():
    dialect = get_dialect("mysql")
    assert dialect.corr_sql("x", "y") == "CORR(x, y)"
    assert dialect.stddev_samp_sql("x") == "STDDEV_SAMP(x)"
    assert "NULLIF" in dialect.regr_slope_sql("y", "x")


def test_statistical_functions_postgres():
    dialect = get_dialect("postgresql")
    assert dialect.corr_sql("x", "y") == "corr(y, x)"
    assert dialect.regr_slope_sql("y", "x") == "regr_slope(y, x)"
    assert dialect.regr_intercept_sql("y", "x") == "regr_intercept(y, x)"


def test_unsupported_engine_raises():
    with pytest.raises(ValueError):
        get_dialect("oracle")
