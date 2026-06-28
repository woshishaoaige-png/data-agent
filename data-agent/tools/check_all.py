"""Run data-agent local checks in the intended order."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
PY = sys.executable

COMMANDS = [
    ("py_compile", [PY, "-m", "py_compile",
                    str(ROOT / "tools" / "db.py"),
                    str(ROOT / "tools" / "gen_catalog.py"),
                    str(ROOT / "tools" / "lint_references.py"),
                    str(ROOT / "tools" / "query_guard.py"),
                    str(ROOT / "tools" / "run_eval_cases.py"),
                    str(ROOT / "tools" / "smoke_eval.py")]),
    ("lint_references", [PY, str(ROOT / "tools" / "lint_references.py")]),
    ("smoke_eval", [PY, str(ROOT / "tools" / "smoke_eval.py")]),
    ("eval_cases", [PY, str(ROOT / "tools" / "run_eval_cases.py")]),
]


def main():
    for name, cmd in COMMANDS:
        print(f"\n=== {name} ===", flush=True)
        subprocess.run(cmd, cwd=PROJECT, check=True)
    print("\nAll data-agent checks passed", flush=True)


if __name__ == "__main__":
    main()
