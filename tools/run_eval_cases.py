"""Run executable data-agent guardrail eval cases."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from query_guard import guard_sql  # noqa: E402
from validate_result import validate_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "eval_cases.json"


def result_text(result):
    return "\n".join(result.errors + result.warnings)


def case_passed(case, result):
    if case.get("expect_status") and result.status != case["expect_status"]:
        return False, f"expected status {case['expect_status']}, got {result.status}"
    if case.get("expect_not_status") and result.status == case["expect_not_status"]:
        return False, f"expected not {case['expect_not_status']}, got {result.status}"
    text = result_text(result)
    for needle in case.get("must_contain", []):
        if needle not in text:
            return False, f"missing required diagnostic {needle!r}; got {text!r}"
    return True, ""


def run_case(case):
    tool = case.get("tool") or case.get("kind") or "query_guard"
    if tool == "query_guard":
        return guard_sql(case["sql"], case.get("intent", ""))
    if tool == "validate_result":
        rows = case.get("rows_json", [])
        return validate_rows(rows, intent=case.get("intent", ""), sql=case.get("sql", ""))
    raise ValueError(f"unsupported eval tool for {case['id']}: {tool}")


def main():
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    failures = []
    for case in payload["cases"]:
        result = run_case(case)
        ok, reason = case_passed(case, result)
        status = "PASS" if ok else "FAIL"
        print(f"{status} {case['id']} [{result.status}]")
        if not ok:
            print(f"  {reason}")
            print(f"  errors={result.errors}")
            print(f"  warnings={result.warnings}")
            failures.append(case["id"])

    total = len(payload["cases"])
    passed = total - len(failures)
    print(f"\n{passed}/{total} eval cases passed")
    if failures:
        raise SystemExit(f"eval case failures: {failures}")


if __name__ == "__main__":
    main()
