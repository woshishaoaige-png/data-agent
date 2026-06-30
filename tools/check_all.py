"""Run data-agent local checks in the intended order."""

import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
PY = sys.executable

COMMANDS = [
    ("py_compile", [PY, "-m", "py_compile",
                    str(ROOT / "tools" / "build_dashboard.py"),
                    str(ROOT / "tools" / "db.py"),
                    str(ROOT / "tools" / "dialects.py"),
                    str(ROOT / "tools" / "context_extractor.py"),
                    str(ROOT / "tools" / "gen_catalog.py"),
                    str(ROOT / "tools" / "lint_references.py"),
                    str(ROOT / "tools" / "query_guard.py"),
                    str(ROOT / "tools" / "profile_table.py"),
                    str(ROOT / "tools" / "run_eval_cases.py"),
                    str(ROOT / "tools" / "smoke_eval.py"),
                    str(ROOT / "tools" / "validate_result.py")]),
    ("lint_references", [PY, str(ROOT / "tools" / "lint_references.py")]),
    ("smoke_eval", [PY, str(ROOT / "tools" / "smoke_eval.py")]),
    ("eval_cases", [PY, str(ROOT / "tools" / "run_eval_cases.py")]),
]


def main():
    env = dict(os.environ)
    env.setdefault("PYTHONPYCACHEPREFIX", "/tmp/data-agent-pycache")
    for name, cmd in COMMANDS:
        print(f"\n=== {name} ===", flush=True)
        subprocess.run(cmd, cwd=PROJECT, check=True, env=env)
    print("\nAll data-agent checks passed", flush=True)


if __name__ == "__main__":
    main()
