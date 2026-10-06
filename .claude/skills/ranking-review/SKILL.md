---
name: ranking-review
description: Run the Agentic TrailGPT Reviewer (re-checks "not included" / "excluded" labels on relevant trials) on the ranking-study development patients until the daily API limit, push the results, and report. Use when the user says "ranking review", "run the reviewer", or /ranking-review.
---

# Ranking review run

Runs the Reviewer stage with `run_parallel.py --stages review` on
`ranking_dev_patients.txt` (6 development patients, 258 trials). It needs the
baseline (TrialGPT matching + aggregation) to be finished for those patients,
which `/ranking-baseline` does.

The development run uses `--min-relevance 0`, so every trial with a negative
label is reviewed once. `evaluate_rankings.py --min-relevance N` then shows
what any higher cutoff would give, without new API calls.

Only run the held-out patients (`ranking_test_patients.txt`) when the user asks
for it by name, with the cutoff they give, and always with `--no-report`.

## Rules

- Never print, echo, log, or commit API keys (`GROQ_API_KEYS`). Do not run
  `env`, `printenv`, or `set`. Scripts here print keys only masked.
- Do not edit code, prompts, or the patient lists during a run. If something
  is broken, stop and report.
- Results go to the branch `claude/daily-results`. Never push to `main`.
- Never report ranking scores (NDCG, P@10) for the held-out patients.

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

```bash
~/trialgpt-venv/bin/python run_parallel.py --patients-file ranking_dev_patients.txt --stages review --min-relevance 0 --max-minutes 8
```

Run it as a foreground command with a 10-minute timeout (600000 ms). Read the
final line, `RESULT status=... remaining_calls=N ...`, then save progress
(skip the commit if `git status --porcelain results/` is empty):

```bash
git add results/
git commit -m "Ranking review: dev <status>, <N> calls left"
git push -u origin claude/daily-results
```

| status | Next |
|---|---|
| `time_up` | Run it again |
| `daily_limit` | Stop for today; go to step 3 |
| `done`, `remaining_calls=0` | Finished; go to step 3 |
| `done`, `remaining_calls>0` | Some trials had errors, or the baseline is not finished for them; run once more, and if nothing changes, report it |

Stop after 30 chunks (about 4 hours) even if work remains, and say so.

## 3. Report

1. If the development run is complete, score it at a few cutoffs:
   ```bash
   ~/trialgpt-venv/bin/python evaluate_rankings.py --variants baseline,reviewed --patients-file ranking_dev_patients.txt --grid
   ~/trialgpt-venv/bin/python evaluate_rankings.py --variants baseline,reviewed --patients-file ranking_dev_patients.txt --min-relevance 50 --grid
   ~/trialgpt-venv/bin/python evaluate_rankings.py --variants baseline,reviewed --patients-file ranking_dev_patients.txt --min-relevance 70 --grid
   ```
2. Commit and push any new files:
   ```bash
   git add results/
   git commit -m "Ranking review: report"
   git push -u origin claude/daily-results
   ```
3. Reply to the user with:
   - progress: development patients complete out of 6, calls left
   - why the run stopped (finished, daily limit, or chunk cap)
   - tokens used today (sum of `tokens=` from the RESULT lines)
   - if complete: for each cutoff (all, 50, 70), NDCG@10 and P@10 of baseline
     and reviewed at TrialGPT's formula (penalty 1, weight 1) and at the best
     grid row, and the Reviewer's extra tokens (%)
   - any errors

   Then end your turn.
