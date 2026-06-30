"""
Lint data-agent references for catalog drift risks.

References may describe semantics and caveats, but they must not copy generated
catalog fields such as exact coverage, flags, date columns, row counts, or units.
Those facts must come from catalog.json at query time.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "references"

BLOCKED_PATTERNS = [
    "Coverage:",
    "Flags:",
    "Date:",
    "Unit:",
    "Rows:",
    "Coverage =",
    "flags=",
    "coverage=",
]


def main():
    failures = []
    for path in sorted(REFS.glob("*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "<catalog-owned>" in line:
                continue
            for pattern in BLOCKED_PATTERNS:
                if pattern in line:
                    failures.append(f"{path.relative_to(ROOT)}:{lineno}: {pattern}")

    if failures:
        print("Reference catalog-drift lint failed:")
        for failure in failures:
            print("  " + failure)
        raise SystemExit(1)
    print("Reference catalog-drift lint passed")


if __name__ == "__main__":
    main()
