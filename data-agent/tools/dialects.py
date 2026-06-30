"""数据库方言适配器。

只承载 SQLAlchemy 反射无法覆盖的方言差异：标识符引用、按今日的日期差函数、
统计函数表达式。
其余结构元数据（表/列/主键）由 SQLAlchemy Inspector 统一处理。
"""


class Dialect:
    name = "base"

    def quote_ident(self, ident):
        raise NotImplementedError

    def fq_table(self, schema, table):
        return f"{self.quote_ident(schema)}.{self.quote_ident(table)}"

    def datediff_today_sql(self, col):
        raise NotImplementedError

    def corr_sql(self, x, y):
        return f"CORR({x}, {y})"

    def stddev_samp_sql(self, expr):
        return f"STDDEV_SAMP({expr})"

    def regr_slope_sql(self, y, x):
        return (
            f"(COUNT(*) * SUM(({x}) * ({y})) - SUM({x}) * SUM({y})) / "
            f"NULLIF(COUNT(*) * SUM(({x}) * ({x})) - SUM({x}) * SUM({x}), 0)"
        )

    def regr_intercept_sql(self, y, x):
        slope = self.regr_slope_sql(y, x)
        return f"(AVG({y}) - ({slope}) * AVG({x}))"


class MySQLDialect(Dialect):
    name = "mysql"

    def quote_ident(self, ident):
        return f"`{ident}`"

    def datediff_today_sql(self, col):
        return f"DATEDIFF(CURDATE(), DATE(MAX({self.quote_ident(col)})))"


class PostgresDialect(Dialect):
    name = "postgresql"

    def quote_ident(self, ident):
        return f'"{ident}"'

    def datediff_today_sql(self, col):
        return f"CURRENT_DATE - MAX({self.quote_ident(col)})::date"

    def corr_sql(self, x, y):
        return f"corr({y}, {x})"

    def stddev_samp_sql(self, expr):
        return f"stddev_samp({expr})"

    def regr_slope_sql(self, y, x):
        return f"regr_slope({y}, {x})"

    def regr_intercept_sql(self, y, x):
        return f"regr_intercept({y}, {x})"


class HiveDialect(Dialect):
    name = "hive"

    def quote_ident(self, ident):
        return f"`{ident}`"

    def datediff_today_sql(self, col):
        return f"datediff(current_date, max({self.quote_ident(col)}))"

    def corr_sql(self, x, y):
        return f"corr({x}, {y})"

    def stddev_samp_sql(self, expr):
        return f"stddev_samp({expr})"


_DIALECTS = {
    "mysql": MySQLDialect,
    "postgresql": PostgresDialect,
    "hive": HiveDialect,
}


def get_dialect(engine_name):
    try:
        return _DIALECTS[engine_name]()
    except KeyError:
        raise ValueError(f"unsupported engine: {engine_name}")
