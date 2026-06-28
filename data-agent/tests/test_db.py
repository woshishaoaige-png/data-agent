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
