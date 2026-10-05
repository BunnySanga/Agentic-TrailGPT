# Held-out criterion test plan

Written 2026-10-05, before any held-out (test split) results were produced.

## Development history (dev patients only)

All tuning used the fixed 300-criterion dev sample (`--split dev --sample 300`).
GPT-4 TrialGPT alone: 83.4%.

| Variant | What it does | Dev accuracy | Fixed / broken |
|---|---|---|---|
| v1 | Assertion + Clarification + Verifier on every criterion | 57.5% | 10 / 88 |
| v2 | Assertion + one Reviewer on "not applicable", "not enough information", "excluded", "not included", and flagged evidence | 83.7% | 26 / 25 |
| v3 | v2 without reviewing "not enough information" labels | 89.0% (computed from v2's outputs; confirmed by a real run) | 21 / 4 |

v3's rule was chosen by looking at the dev sample, so its dev score is
optimistic. The held-out test decides.

## Test

- Data: the 12 patients in `criteria_test_patients.txt` (264 criteria),
  never used for tuning.
- Primary comparison: **v3 vs GPT-4 alone** on accuracy against physicians,
  with labels fixed / broken and the exact McNemar test.
- Also reported: v1 and v2 on the same rows (ablations), evidence-sentence
  precision/recall, tokens per criterion.
- No prompt or code changes after seeing test results. Whatever the test
  shows is the reported result, including if v3 does not beat GPT-4.

Commands: `/criteria-test v1 test`, `/criteria-test v2 test`, `/criteria-test v3 test`.
