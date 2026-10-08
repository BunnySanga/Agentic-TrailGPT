---
name: ranking-heldout-review
description: Run the Reviewer once on the 46 held-out ranking patients (the ablation in RANKING_STUDY_PLAN.md), after the held-out TrialGPT run has finished, until the daily API limit; push the results and report progress without scores. Use when the user says "held-out review", "run the reviewer on held-out", or /ranking-heldout-review.
---

# Held-out Reviewer run (ablation in RANKING_STUDY_PLAN.md)

Runs `run_parallel.py --stages review --min-relevance 0` on
`ranking_test_patients.txt` (12 patients), then
`ranking_test_extra_patients.txt` (34 patients). Every trial with a
"not included" or "excluded" label is reviewed once; cutoffs 50 and 70 are
scored later from the same run. This is an ablation: it does not change the
chosen system.

It needs TrialGPT (matching + aggregation) finished for those patients, which
`/ranking-heldout none` does. If that run still has calls left, stop and tell
the user to finish it first.

Results resume from earlier days, so the user types the same command again
tomorrow if today's API limit stops the run.

## Rules

- Never print, echo, log, or commit API keys (`GROQ_API_KEYS`). Do not run
  `env`, `printenv`, or `set`. Scripts here print keys only masked.
- Do not edit code, prompts, the plan, or the patient lists. If something is
  broken, stop and report.
- Results go to the branch `claude/daily-results`. Never push to `main`.
- **Never report ranking scores (NDCG, P@10) for these patients**, and never
  run `evaluate_rankings.py` on them. Always pass `--no-report`.

## 1. Prepare

Work from the repository root.

1. If `~/trialgpt-venv/bin/python` does not exist, create it:
   ```bash
   python3 -m venv ~/trialgpt-venv && ~/trialgpt-venv/bin/pip install -q -r requirements-run.txt && ~/trialgpt-venv/bin/python -m nltk.downloader -q punkt
   ```
2. Switch to the results branch:
   ```bash
   git fetch origin
   ```
   If `git ls-remote --exit-code --heads origin claude/daily-results` succeeds:
   ```bash
   git checkout -B claude/daily-results origin/claude/daily-results
   git merge --no-edit origin/main
   ```
   Otherwise:
   ```bash
   git checkout -B claude/daily-results origin/main
   ```
3. Check configuration and keys:
   ```bash
   ~/trialgpt-venv/bin/python check_groq_keys.py
   ```
   Expect `Model: openai/gpt-oss-120b`, `Reasoning effort: low`, and every
   key `OK`. Otherwise stop and tell the user what to fix in the cloud
   environment (see CLOUD_RUN.md).
4. Confirm TrialGPT is finished for both lists (no API calls):
   ```bash
   ~/trialgpt-venv/bin/python run_parallel.py --patients-file ranking_test_patients.txt --stages match,aggregate --dry-run
   ~/trialgpt-venv/bin/python run_parallel.py --patients-file ranking_test_extra_patients.txt --stages match,aggregate --dry-run
   ```
   Both must end with `remaining_calls=0`. Otherwise stop and tell the user to
   run `/ranking-heldout none` first.

## 2. Run in chunks

```bash
~/trialgpt-venv/bin/python run_parallel.py --patients-file ranking_test_patients.txt --stages review --min-relevance 0 --max-minutes 8 --no-report
```

When it reports `status=done remaining_calls=0`, run the same command with
`--patients-file ranking_test_extra_patients.txt`.

Run each as a foreground command with a 10-minute timeout (600000 ms). Read
the final line, `RESULT status=... remaining_calls=N ...`, then save progress
(skip the commit if `git status --porcelain results/` is empty):

```bash
git add results/
git commit -m "Ranking held-out review: <test|extra> <status>, <N> calls left"
git push -u origin claude/daily-results
```

| status | Next |
|---|---|
| `time_up` | Run the same list again |
| `daily_limit` | Stop for today; go to step 3 |
| `done`, `remaining_calls=0` | That list is finished: move from test to extra, or after extra go to step 3 |
| `done`, `remaining_calls>0` | Trials had errors; run once more, and if nothing changes, report the errors |

Stop after 30 chunks (about 4 hours) even if work remains, and say so.

## 3. Report

Reply to the user with:

- progress for each list: patients complete out of 12 and 34, and calls left
- why the run stopped (finished, daily limit, or chunk cap)
- tokens used today (sum of `tokens=` from the RESULT lines)
- any errors

Do not give any ranking score. When both lists are finished, say that phase 3
(scoring once, as written in RANKING_STUDY_PLAN.md) can start. Then end your turn.
