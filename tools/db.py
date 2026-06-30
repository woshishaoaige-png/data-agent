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
