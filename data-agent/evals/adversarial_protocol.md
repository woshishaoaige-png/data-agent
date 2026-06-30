# Adversarial Eval Protocol

Use this protocol whenever data-agent adds a new SQL capability, guardrail, or
result validator.

## Round 1: Attack Design

Run at least two independent adversarial reviewers:

- one focused on SQL generation and static guard failures;
- one focused on executed result shape and answer-validation failures.

Each reviewer proposes executable cases with:

- `id`
- `tool`: `query_guard` or `validate_result`
- `intent`
- `sql` or `rows_json`
- expected status
- required diagnostic substring

## Round 2: Implementation Attack

After the first implementation and local eval pass, run at least two reviewers
again against the changed files. The second round should look for:

- false negatives: risky SQL/result shapes that still pass;
- false positives: safe staged SQL that is blocked;
- brittle diagnostics that pass only by accident;
- missing reference rules that leave the agent without guidance.

Only promote a case into `eval_cases.json` when the diagnostic is stable and
the expected behavior is clear.

## Promotion Rules

- Prefer high-confidence cases over broad parser-like checks.
- Keep `query_guard` static and conservative.
- Put semantic/result facts in `validate_result`.
- If an eval requires real database contents, convert it to `rows_json` or make
  the expectation about static diagnostics only.
- Every promoted diagnostic should appear in a test or eval, not only in docs.
