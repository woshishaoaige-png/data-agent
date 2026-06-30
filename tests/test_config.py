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
          a:
            engine: mysql
            schemas: [S1]
          b:
            engine: postgresql
            schemas: [S2]
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
          a:
            engine: mysql
            password: ${NOPE_VAR}
            schemas: [S1]
    """)
    with pytest.raises(KeyError):
        cfg.get_active_datasource(p)


def test_unknown_active_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_AGENT_DATASOURCE", raising=False)
    p = _write(tmp_path, """
        active: missing
        datasources:
          a:
            engine: mysql
            schemas: [S1]
    """)
    with pytest.raises(ValueError):
        cfg.get_active_datasource(p)
