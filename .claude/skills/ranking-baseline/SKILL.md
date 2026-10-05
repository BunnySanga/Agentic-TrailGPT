---
name: ranking-baseline
description: Run baseline TrialGPT (matching + aggregation, no agents) for the ranking-study patients until the daily API limit, push the results, and report progress. Use when the user says "ranking baseline", "continue the baseline", or /ranking-baseline.
---

# Ranking baseline run

Runs official TrialGPT matching and aggregation (no agents) with
`run_parallel.py --stages match,aggregate` for:

1. `ranking_dev_patients.txt`: 6 development patients, 258 trials. Run first.
2. `ranking_test_patients.txt`: 12 held-out patients, 354 trials.

Results resume from earlier days, so the user can type `/ranking-baseline`
again tomorrow if today's API limit stops the run.

## Rules

- Never print, echo, log, or commit API keys (`GROQ_API_KEYS`). Do not run
  `env`, `printenv`, or `set`. Scripts here print keys only masked.
- Do not edit code, prompts, or the patient lists during a run. If something
  is broken, stop and report.
- Results go to the branch `claude/daily-results`. Never push to `main`.
- **Never report ranking scores (NDCG, P@10) for the held-out patients.** They
  are scored once, at the very end of the study. Always pass `--no-report`
  when running `ranking_test_patients.txt`, and do not run
  `evaluate_rankings.py` on it.

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

## 2. Run in chunks

Development patients first:

```bash
~/trialgpt-venv/bin/python run_parallel.py --patients-file ranking_dev_patients.txt --stages match,aggregate --max-minutes 8
```

When the development list reports `status=done remaining_calls=0`, switch to
the held-out patients:

```bash
~/trialgpt-venv/bin/python run_parallel.py --patients-file ranking_test_patients.txt --stages match,aggregate --max-minutes 8 --no-report
```

Run each as a foreground command with a 10-minute timeout (600000 ms). Read
the final line, `RESULT status=... remaining_calls=N ...`, then save progress
(skip the commit if `git status --porcelain results/` is empty):

```bash
git add results/
git commit -m "Ranking baseline: <dev|test> <status>, <N> calls left"
git push -u origin claude/daily-results
```

| status | Next |
|---|---|
| `time_up` | Run the same list again |
| `daily_limit` | Stop for today; go to step 3 |
| `done`, `remaining_calls=0` | That list is finished: move from dev to test, or after test go to step 3 |
| `done`, `remaining_calls>0` | Trials had errors; run once more, and if nothing changes, report the errors |

Stop after 30 chunks (about 4 hours) even if work remains, and say so.

## 3. Report

1. If the development list is complete, score it (development patients only):
   ```bash
   ~/trialgpt-venv/bin/python evaluate_rankings.py --variants baseline --patients-file ranking_dev_patients.txt
   ```
2. Commit and push any new files:
   ```bash
   git add results/
   git commit -m "Ranking baseline: report"
   git push -u origin claude/daily-results
   ```
3. Reply to the user with:
   - progress: development and held-out patients complete out of 6 and 12,
     and calls left in each list
   - why the run stopped (finished, daily limit, or chunk cap)
   - tokens used today (sum of `tokens=` from the RESULT lines) and how many
     more days the remaining calls need at today's pace
   - if the development list is complete: its baseline NDCG@10 and P@10,
     overall and per patient, and the token cost per trial
   - any errors

   Do not give any ranking score for the held-out patients. Then end your turn.
