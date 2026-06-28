# 多数据库可配置改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 data-agent 的数据库连接与 catalog 自省可配置，支持 MySQL/PostgreSQL/Hive，护栏层与 catalog.json 格式保持不变。

**Architecture:** YAML 声明多数据源 → config.py 解析并选 active 源 → db.py 按配置建连 → gen_catalog.py 用 SQLAlchemy Inspector 反射 + 小方言适配器(dialects.py) 自省，产出同格式 catalog.json。方言差异只剩"标识符引用 + 日期差函数"两类，收进 dialects.py。

**Tech Stack:** Python 3.14 (dev venv), SQLAlchemy (Inspector 反射), PyYAML, pytest, mysqlconnector (现有), psycopg2/PyHive (可选)。

**约定：** 所有命令用 dev venv 的解释器 `/Users/weini/.venvs/dev/bin/python`（即用户的 `dev` 环境）。若该路径不对，用 `python` 并确保在 dev venv 激活下运行。项目根：`/Users/weini/Documents/agent_flow/PROJECTS/data-agent`。

---

## File Structure

- `tools/dialects.py` (新增) — 方言适配器，纯函数，无 DB 连接，最底层。
- `tools/config.py` (新增) — 读 yaml + env 插值 + 选 active 源。
- `tools/db.py` (改) — build_url 纯函数 + get_engine，去 _shared 依赖。
- `tools/gen_catalog.py` (改) — Inspector 反射 + dialect，SCHEMAS 从 config。
- `databases.example.yaml` (新增) — 配置模板（入库）。
- `tests/test_dialects.py` / `tests/test_config.py` / `tests/test_db.py` (新增) — 离线单测。
- `.gitignore` (改) — 加入真实 `databases.yaml`。
- `README.md` (改) — 多库配置说明。

---

## Task 1: 方言适配器 dialects.py

**Files:**
- Create: `tools/dialects.py`
- Test: `tests/test_dialects.py`

- [ ] **Step 1: 写失败测试**

`tests/test_dialects.py`:
```python
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


def test_unsupported_engine_raises():
    with pytest.raises(ValueError):
        get_dialect("oracle")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/Users/weini/.venvs/dev/bin/python -m pytest tests/test_dialects.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'dialects'`）

- [ ] **Step 3: 实现 dialects.py**

`tools/dialects.py`:
```python
"""数据库方言适配器。

只承载 SQLAlchemy 反射无法覆盖的两类方言差异：标识符引用、按今日的日期差函数。
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


class HiveDialect(Dialect):
    name = "hive"

    def quote_ident(self, ident):
        return f"`{ident}`"

    def datediff_today_sql(self, col):
        return f"datediff(current_date, max({self.quote_ident(col)}))"


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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/Users/weini/.venvs/dev/bin/python -m pytest tests/test_dialects.py -v`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git -C /Users/weini/Documents/agent_flow/PROJECTS add data-agent/tools/dialects.py data-agent/tests/test_dialects.py
git -C /Users/weini/Documents/agent_flow/PROJECTS commit -m "feat: add cross-dialect adapter for data-agent introspection"
```

---

## Task 2: 配置加载 config.py + 模板

**Files:**
- Create: `tools/config.py`, `databases.example.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: 写配置模板**

`databases.example.yaml`:
```yaml
# data-agent 多数据源配置模板。
# 复制为 databases.yaml 并填写真实值；密码用 ${ENV_VAR} 形式走环境变量，不要写明文。
active: local_mysql                 # 可被环境变量 DATA_AGENT_DATASOURCE 覆盖

datasources:
  local_mysql:
    engine: mysql                   # mysql | postgresql | hive
    driver: mysqlconnector
    host: 127.0.0.1
    port: 3306
    user: root
    password: ${MYSQL_PWD}
    schemas: [Stock, finance]       # MySQL: database 名列表

  warehouse_pg:
    engine: postgresql
    driver: psycopg2
    host: pg.internal
    port: 5432
    user: analyst
    password: ${PG_PWD}
    database: analytics             # PG 是 database>schema 两层
    schemas: [public, finance]

  lake_hive:
    engine: hive
    driver: hive
    host: hive.internal
    port: 10000
    schemas: [default]
```

- [ ] **Step 2: 写失败测试**

`tests/test_config.py`:
```python
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import config as cfg  # noqa: E402


def _write(tmp_path, body):
    p = tmp_path / "databases.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_active_and_env_interp(tmp_path, monkeypatch):
    p = _write(tmp_path, """
        active: a
        datasources:
          a:
            engine: mysql
            password: ${PWD_X}
            schemas: [S1]
    """)
    monkeypatch.setenv("PWD_X", "secret")
    name, ds = cfg.get_active_datasource(p)
    assert name == "a"
    assert ds["password"] == "secret"
    assert ds["schemas"] == ["S1"]


def test_env_overrides_active(tmp_path, monkeypatch):
    p = _write(tmp_path, """
        active: a
        datasources:
          a: {engine: mysql, schemas: [S1]}
          b: {engine: postgresql, schemas: [S2]}
    """)
    monkeypatch.setenv("DATA_AGENT_DATASOURCE", "b")
    name, ds = cfg.get_active_datasource(p)
    assert name == "b"
    assert ds["engine"] == "postgresql"


def test_missing_env_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_VAR", raising=False)
    p = _write(tmp_path, """
        active: a
        datasources:
          a: {engine: mysql, password: ${NOPE_VAR}, schemas: [S1]}
    """)
    with pytest.raises(KeyError):
        cfg.get_active_datasource(p)


def test_unknown_active_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_AGENT_DATASOURCE", raising=False)
    p = _write(tmp_path, """
        active: missing
        datasources:
          a: {engine: mysql, schemas: [S1]}
    """)
    with pytest.raises(ValueError):
        cfg.get_active_datasource(p)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `/Users/weini/.venvs/dev/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'config'` 或 `yaml`）。若缺 yaml：`/Users/weini/.venvs/dev/bin/python -m pip install pyyaml`

- [ ] **Step 4: 实现 config.py**

`tools/config.py`:
```python
"""读 databases.yaml，解析 ${ENV} 插值，选 active 数据源。"""

import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "databases.yaml"
ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _interp(value):
    if not isinstance(value, str):
        return value

    def repl(m):
        env = m.group(1)
        if env not in os.environ:
            raise KeyError(f"env var not set for config: {env}")
        return os.environ[env]

    return ENV_RE.sub(repl, value)


def _interp_deep(obj):
    if isinstance(obj, dict):
        return {k: _interp_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interp_deep(v) for v in obj]
    return _interp(obj)


def load_config(path=None):
    path = Path(path) if path else DEFAULT_CONFIG
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def get_active_datasource(path=None):
    raw = load_config(path)
    name = os.getenv("DATA_AGENT_DATASOURCE") or raw.get("active")
    if not name:
        raise ValueError(
            "no active datasource (set 'active' in yaml or DATA_AGENT_DATASOURCE)"
        )
    sources = raw.get("datasources", {})
    if name not in sources:
        raise ValueError(f"datasource not found: {name}")
    return name, _interp_deep(sources[name])
```

- [ ] **Step 5: 运行测试确认通过**

Run: `/Users/weini/.venvs/dev/bin/python -m pytest tests/test_config.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git -C /Users/weini/Documents/agent_flow/PROJECTS add data-agent/tools/config.py data-agent/databases.example.yaml data-agent/tests/test_config.py
git -C /Users/weini/Documents/agent_flow/PROJECTS commit -m "feat: add yaml datasource config with env interpolation"
```

---

## Task 3: db.py 改造（build_url + get_engine）

**Files:**
- Modify: `tools/db.py`（整体重写）
- Test: `tests/test_db.py`

- [ ] **Step 1: 写失败测试**

`tests/test_db.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from db import build_url  # noqa: E402


def test_build_url_mysql():
    ds = {"engine": "mysql", "driver": "mysqlconnector", "user": "root",
          "password": "p", "host": "127.0.0.1", "port": 3306, "schemas": ["Stock"]}
    assert build_url(ds, "Stock") == "mysql+mysqlconnector://root:p@127.0.0.1:3306/Stock"


def test_build_url_pg_uses_database():
    ds = {"engine": "postgresql", "driver": "psycopg2", "user": "u",
          "password": "p", "host": "h", "port": 5432,
          "database": "analytics", "schemas": ["public"]}
    assert build_url(ds, "public") == "postgresql+psycopg2://u:p@h:5432/analytics"


def test_build_url_hive_no_auth():
    ds = {"engine": "hive", "driver": "hive", "host": "h",
          "port": 10000, "schemas": ["default"]}
    assert build_url(ds, "default") == "hive://h:10000/default"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/Users/weini/.venvs/dev/bin/python -m pytest tests/test_db.py -v`
Expected: FAIL（`ImportError: cannot import name 'build_url'`）

- [ ] **Step 3: 重写 db.py**

`tools/db.py`（整体替换为）:
```python
"""data-agent 唯一数据库入口。

按 databases.yaml 的 active 数据源建连，支持 mysql/postgresql/hive。
环境变量 DATA_AGENT_DB_URL 可整体覆盖；跨库查询用全限定名。
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).parent))
from config import get_active_datasource  # noqa: E402

DRIVERS = {
    "mysql": "mysql+mysqlconnector",
    "postgresql": "postgresql+psycopg2",
    "hive": "hive",
}


def build_url(ds, schema):
    engine = ds["engine"]
    driver = ds.get("driver")
    prefix = f"{engine}+{driver}" if driver and engine != "hive" else DRIVERS[engine]
    user = ds.get("user", "")
    pwd = ds.get("password", "")
    auth = f"{user}:{pwd}@" if user else ""
    host = ds.get("host", "")
    port = ds.get("port", "")
    hostport = f"{host}:{port}" if port else host
    # MySQL: schema 即 database；PG/Hive: 连 database(默认回退到 schema)，schema 查询时限定。
    db = schema if engine == "mysql" else ds.get("database", schema)
    return f"{prefix}://{auth}{hostport}/{db}"


def get_engine(schema=None):
    """data-agent 专用连接。DATA_AGENT_DB_URL 可整体覆盖。"""
    override = os.getenv("DATA_AGENT_DB_URL")
    if override:
        return create_engine(override, pool_pre_ping=True)
    _, ds = get_active_datasource()
    if schema is None:
        schema = ds["schemas"][0]
    return create_engine(build_url(ds, schema), pool_pre_ping=True)


if __name__ == "__main__":
    from sqlalchemy import text

    with get_engine().connect() as conn:
        r = conn.execute(text("SELECT 1 AS x")).fetchone()
        print("data-agent DB OK:", r.x)
```

- [ ] **Step 4: 运行单测确认通过**

Run: `/Users/weini/.venvs/dev/bin/python -m pytest tests/test_db.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 准备真实 databases.yaml 并实跑连接自检**

```bash
cp /Users/weini/Documents/agent_flow/PROJECTS/data-agent/databases.example.yaml \
   /Users/weini/Documents/agent_flow/PROJECTS/data-agent/databases.yaml
export MYSQL_PWD=12345678
cd /Users/weini/Documents/agent_flow/PROJECTS/data-agent && /Users/weini/.venvs/dev/bin/python tools/db.py
```
Expected: `data-agent DB OK: 1`

- [ ] **Step 6: 提交（不含真实 databases.yaml）**

```bash
git -C /Users/weini/Documents/agent_flow/PROJECTS add data-agent/tools/db.py data-agent/tests/test_db.py
git -C /Users/weini/Documents/agent_flow/PROJECTS commit -m "refactor: build db connection from yaml config, drop _shared dependency"
```

---

## Task 4: gen_catalog.py 改造（Inspector + dialect）

**Files:**
- Modify: `tools/gen_catalog.py`

- [ ] **Step 1: 改 import 与 SCHEMAS 来源**

把文件顶部（第 22-34 行附近）的 import 段与 SCHEMAS 定义改为：
```python
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
```
删除原 `SCHEMAS = ["Stock", "finance"]` 这一行（改到 main() 里从 config 取）。

- [ ] **Step 2: 用 dialect 改写三个聚合辅助函数**

把 `_distinct_count` / `_date_bounds` / `_freshness_days` 改为接收 `dialect` 与 `(schema, table)`，用方言生成 SQL：
```python
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
```

- [ ] **Step 3: 改写 introspect_table 用 Inspector**

把 `introspect_table` 签名与列/主键/行数获取段改为用 SQLAlchemy Inspector，并把后续所有 `_distinct_count(conn, fq, col)` 调用改为 `_distinct_count(conn, dialect, schema, table, col)` 等：
```python
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
```

- [ ] **Step 4: 改写 main() 用 Inspector 列举表/视图、SCHEMAS 从 config**

把 `main()` 里建 engine 到遍历 schema 的段改为：
```python
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
```
（注意：原来 engine 缺省连 Stock；现需保证 get_engine() 能跨 schema 反射。MySQL 下 Inspector 用 `schema=` 参数即可跨 database 反射，连哪个 database 不影响。）

- [ ] **Step 5: 实跑重新生成 catalog 并做关键字段回归对比**

先备份旧 catalog，再重新生成：
```bash
cd /Users/weini/Documents/agent_flow/PROJECTS/data-agent
export MYSQL_PWD=12345678
git show HEAD:data-agent/catalog.json > /tmp/catalog_old.json
/Users/weini/.venvs/dev/bin/python tools/gen_catalog.py
```
然后跑对比脚本（关键字段必须完全一致，column type 文本差异忽略）：
```bash
/Users/weini/.venvs/dev/bin/python - <<'PY'
import json
old = json.load(open("/tmp/catalog_old.json"))
new = json.load(open("catalog.json"))
KEYS = ["coverage","flags","row_count","distinct_stocks","distinct_dates",
        "date_min","date_max","unit","stock_col","board_col","freshness_days"]
diffs = []
for sch, tbls in old["schemas"].items():
    for t, info in tbls.items():
        ninfo = new["schemas"].get(sch, {}).get(t)
        if ninfo is None:
            diffs.append(f"{sch}.{t}: MISSING in new"); continue
        for k in KEYS:
            if info.get(k) != ninfo.get(k):
                diffs.append(f"{sch}.{t}.{k}: {info.get(k)!r} -> {ninfo.get(k)!r}")
# 新表（视图等）允许出现
for sch, tbls in new["schemas"].items():
    for t in tbls:
        if t not in old["schemas"].get(sch, {}):
            diffs.append(f"{sch}.{t}: NEW in new (ok if expected)")
print("DIFF COUNT:", len(diffs))
for d in diffs:
    print(" ", d)
PY
```
Expected: 关键字段 DIFF 应为 0（除可能的 "NEW in new" 提示）。若有关键字段差异，停下排查（多半是 dialect SQL 或 Inspector type 影响了 `_pick_date_col`）。

- [ ] **Step 6: 跑 check_all 全绿**

Run: `cd /Users/weini/Documents/agent_flow/PROJECTS/data-agent && export MYSQL_PWD=12345678 && /Users/weini/.venvs/dev/bin/python tools/check_all.py`
Expected: `All data-agent checks passed`（30 eval + smoke + lint）

- [ ] **Step 7: 提交**

```bash
git -C /Users/weini/Documents/agent_flow/PROJECTS add data-agent/tools/gen_catalog.py data-agent/catalog.json
git -C /Users/weini/Documents/agent_flow/PROJECTS commit -m "refactor: introspect catalog via SQLAlchemy Inspector and dialect adapter"
```

---

## Task 5: .gitignore + README + 全量单测收尾

**Files:**
- Modify: `.gitignore`, `README.md`

- [ ] **Step 1: 更新 .gitignore**

在 `data-agent/.gitignore` 追加（避免真实凭证入库）：
```
databases.yaml
```

- [ ] **Step 2: README 增加多数据库配置说明**

在 `README.md` 末尾追加一节：
```markdown
## 多数据库配置

data-agent 的连接与自省支持 MySQL / PostgreSQL / Hive，通过 `databases.yaml` 配置。

1. 复制模板：`cp databases.example.yaml databases.yaml`
2. 填写数据源；密码用 `${ENV_VAR}` 引用环境变量，不要写明文。
3. 设置激活源：yaml 的 `active` 字段，或环境变量 `DATA_AGENT_DATASOURCE`。
4. 导出密码后生成 catalog：

   ```bash
   export MYSQL_PWD=...           # 对应 yaml 里的 ${MYSQL_PWD}
   python tools/gen_catalog.py
   ```

说明：
- MySQL 的 `schemas` 是 database 名列表；PostgreSQL 需额外 `database` 字段，`schemas` 指 PG schema。
- `psycopg2` / `PyHive` 仅在用对应引擎时安装。
- 视图 `sql/create_views.sql` 与单位/维度业务知识是 A 股数据集特定的，换库时需相应调整。
- `DATA_AGENT_DB_URL` 可整体覆盖连接串。
```

- [ ] **Step 3: 跑全量单测 + check_all 最终确认**

Run:
```bash
cd /Users/weini/Documents/agent_flow/PROJECTS/data-agent
export MYSQL_PWD=12345678
/Users/weini/.venvs/dev/bin/python -m pytest tests/ -v
/Users/weini/.venvs/dev/bin/python tools/check_all.py
```
Expected: pytest 全 PASS（16 项），check_all `All data-agent checks passed`

- [ ] **Step 4: 提交**

```bash
git -C /Users/weini/Documents/agent_flow/PROJECTS add data-agent/.gitignore data-agent/README.md
git -C /Users/weini/Documents/agent_flow/PROJECTS commit -m "docs: document multi-database config and ignore real databases.yaml"
```

- [ ] **Step 5: 推送**

```bash
git -C /Users/weini/Documents/agent_flow/PROJECTS push
```

---

## 验收标准

- MySQL 下 `tools/db.py` 自检输出 `data-agent DB OK: 1`。
- 重新生成的 `catalog.json` 关键字段（coverage/flags/distinct/dates/unit/row_count）与改造前一致。
- `check_all.py` 全绿（30 eval + smoke + lint）。
- `tests/` 全部 pytest 通过（dialects 9 + config 4 + db 3）。
- 护栏层文件（query_guard / join_policy / SKILL / evals / references / create_views）零改动。
- 真实 `databases.yaml` 不入库，`databases.example.yaml` 入库。
