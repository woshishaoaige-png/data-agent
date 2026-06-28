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
