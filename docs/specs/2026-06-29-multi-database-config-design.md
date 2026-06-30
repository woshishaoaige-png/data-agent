# data-agent 多数据库可配置改造 设计

- 日期：2026-06-29
- 状态：已批准设计
- 范围：连接层可配置 + 自省跨方言（不外置 A 股业务知识）

## 背景与问题

当前 data-agent 的数据库连接为本地 MySQL 定制：

- `tools/db.py` 硬写 `mysql+mysqlconnector://` 驱动，凭证从 `_shared/mysql_config.py` 取。
- `tools/gen_catalog.py` 深度耦合 MySQL：`information_schema` 查询、反引号标识符、
  `DATEDIFF(CURDATE(), ...)`、`COLUMN_KEY='PRI'` 主键识别、`SCHEMAS=["Stock","finance"]` 硬编码。
- `sql/create_views.sql` 用 MySQL 反引号语法，内容是 A 股业务视图。

目录已从 `StockTradebyZ/data-agent` 移到 `PROJECTS/data-agent`，
`db.py` 依赖的 `parents[2]/_shared/mysql_config.py` 相对路径已断。

目标：连接可配置（MySQL/PostgreSQL/Hive 等），catalog 自省能跨这些方言正确工作。
MySQL 示例连接只是开发期样例，不应写死。

## 决策

1. 范围：连接 + 自省跨方言。视图与业务规则仍是这套 A 股数据，不外置业务知识。
2. 可测实例：当前只有 MySQL。MySQL 实跑验证；PG/Hive 做方言适配层 + 离线单元测试。
3. 配置形式：YAML 配置文件。
4. 自省机制：SQLAlchemy Inspector 反射 + 小方言适配器。

## 关键洞察

护栏层（`query_guard.py`、`policies/join_policy.json`、`SKILL.md`、`evals/*`、`references/*`）
只消费 `catalog.json`，与底层引擎无关。只要 `catalog.json` 格式不变，这些文件本次零改动。
风险集中在 `db.py` + `gen_catalog.py`。

## 架构

```
databases.yaml          多数据源声明(engine/driver/host/port/db/schemas)，密码走 ${ENV} 插值
   |
tools/config.py         读 yaml + 解析 ${ENV} + 选 active 数据源
   |
tools/db.py             get_engine() 按配置建连，不再依赖 _shared
   |
tools/dialects.py       Dialect 适配器：quote_ident() + datediff_today_sql() + fq_table()
   |
tools/gen_catalog.py    SQLAlchemy Inspector 反射 + Dialect，SCHEMAS 从 config，产出同格式 catalog.json
   |
catalog.json (格式不变) -> query_guard / SKILL / eval / references 全部不动
```

## 组件设计

### databases.yaml

```yaml
active: local_mysql                  # 可被环境变量 DATA_AGENT_DATASOURCE 覆盖

datasources:
  local_mysql:
    engine: mysql                    # mysql | postgresql | hive
    driver: mysqlconnector
    host: 127.0.0.1
    port: 3306
    user: root
    password: ${MYSQL_PWD}           # 环境变量插值，明文不入库
    schemas: [Stock, finance]        # MySQL: database 名列表

  warehouse_pg:
    engine: postgresql
    driver: psycopg2
    host: pg.internal
    port: 5432
    user: analyst
    password: ${PG_PWD}
    database: analytics              # PG 是 database>schema 两层
    schemas: [public, finance]

  lake_hive:
    engine: hive
    driver: hive
    host: hive.internal
    port: 10000
    schemas: [default]
```

命名差异：MySQL 的 database 当一层 schema 用，`schemas` 即 database 列表；
PG 是 database>schema 两层，多一个 `database` 字段，`schemas` 指 PG schema。
真实 `databases.yaml` 进 `.gitignore`，入库 `databases.example.yaml` 作模板。

### tools/config.py

- 读 `databases.yaml`，解析 `${ENV}` 插值（仅对选中数据源插值，避免未用源 env 缺失报错）。
- 选 active：默认 yaml 的 `active`，可被环境变量 `DATA_AGENT_DATASOURCE` 覆盖。
- 返回 (name, datasource_dict)。

### tools/db.py

- `build_url(ds, schema)` 纯函数构造 SQLAlchemy URL（便于离线测试）。
- `get_engine(schema=None)` 用 active 配置建连；schema 缺省取 `schemas[0]`。
- 移除 `_shared` 依赖（修复断链）。保留 `DATA_AGENT_DB_URL` 整体覆盖。

### tools/dialects.py

| 方法 | MySQL | PostgreSQL | Hive |
|---|---|---|---|
| `quote_ident("x")` | `` `x` `` | `"x"` | `` `x` `` |
| `datediff_today_sql(col)` | `DATEDIFF(CURDATE(), DATE(MAX(\`col\`)))` | `CURRENT_DATE - MAX("col")::date` | `datediff(current_date, max(\`col\`))` |
| `fq_table(s, t)` | `` `s`.`t` `` | `"s"."t"` | `` `s`.`t` `` |

`get_dialect(engine_name)` 工厂返回对应实现，未知引擎抛 ValueError。

### tools/gen_catalog.py

- 表/视图：`inspector.get_table_names(schema)` + `get_view_names(schema)`，区分 type。
- 列：`inspector.get_columns(table, schema)`（type 用 `str(col["type"])`）；主键：`get_pk_constraint`（Hive 空，可接受）。
- 聚合（行数/distinct/min-max/freshness）执行 SQL，标识符与日期差经 Dialect 生成方言正确版本。
- `SCHEMAS` 从 config 读。
- `UNIT_MAP`/`DIMENSION_OVERRIDES`/`DATE_OVERRIDES` 是 A 股业务知识，保留；标注跨非 A 股库需调整。

## 不在本次范围

- `create_views.sql` 保留 MySQL 版（A 股业务视图）；跨库时视图需各自重写。
- 把业务知识外置成通用配置（完整数据库无关框架）不做。

## 验证策略

- MySQL（实跑）：重跑 `gen_catalog.py`，新旧 catalog 的关键字段（coverage/flags/distinct_stocks/
  distinct_dates/date_min/date_max/unit/row_count）必须一致；`column type` 文本可能因 Inspector
  规范化出现大小写/格式变化，属预期。`check_all.py` 全绿。
- PG/Hive（离线单测）：`tests/test_dialects.py` 锁方言 SQL 正确性，不连真库。

## 依赖与兼容

- 新增 `PyYAML`。`psycopg2`/`PyHive` 可选（用对应引擎时装）。
- 保留 `DATA_AGENT_DB_URL`。移除 `_shared` 依赖。

## 文件改动清单

新增：`databases.example.yaml`、`tools/config.py`、`tools/dialects.py`、
`tests/test_dialects.py`、`tests/test_config.py`、`tests/test_db.py`

修改：`tools/db.py`、`tools/gen_catalog.py`、`README.md`、`.gitignore`

不动：`tools/query_guard.py`、`policies/join_policy.json`、`SKILL.md`、`evals/*`、
`references/*`、`sql/create_views.sql`
