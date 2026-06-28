"""
data-agent 唯一数据库入口（阶段 0 / G4）

所有 data-agent 的查询与工具只准从这里取连接：
  - 统一使用 mysqlconnector 驱动（MySQL 9.x caching_sha2 兼容）
  - 不使用 pymysql，避免双驱动在 Decimal/日期/NULL 上的类型映射不一致
  - 现有 42 个采集脚本不受影响，仍走 _shared/mysql_config.py 各自的入口

跨库查询用全限定名（finance.sentiment_index），engine 默认连 Stock。
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine

# 复用 _shared 里的凭据唯一源头，但驱动固定为 mysqlconnector
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from _shared.mysql_config import DB_USER, PWD_VAR, DB_HOST, DB_PORT  # noqa: E402


def get_engine(database: str = "Stock"):
    """data-agent 专用连接。环境变量 DATA_AGENT_DB_URL 可整体覆盖。"""
    url = os.getenv(
        "DATA_AGENT_DB_URL",
        f"mysql+mysqlconnector://{DB_USER}:{PWD_VAR}@{DB_HOST}:{DB_PORT}/{database}",
    )
    return create_engine(url, pool_pre_ping=True)


if __name__ == "__main__":
    from sqlalchemy import text

    with get_engine().connect() as conn:
        r = conn.execute(text("SELECT 1 AS x")).fetchone()
        print("data-agent DB OK:", r.x)
