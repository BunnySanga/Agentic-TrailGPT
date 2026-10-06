---
name: ranking-heldout
description: Run the ranking study's held-out patients (TrialGPT matching + aggregation, then the Reviewer at the chosen cutoff) until the daily API limit, push the results, and report progress without scores. Use when the user says "held-out run", "continue the held-out", or /ranking-heldout <cutoff|none>.
---

# Held-out ranking run (phase 2 of RANKING_STUDY_PLAN.md)

Argument: the Reviewer cutoff chosen in phase 1, recorded under "Chosen
settings" in `RANKING_STUDY_PLAN.md`, for example `/ranking-heldout 50`.
`none` means the plan dropped the Reviewer; then run TrialGPT only.

If no argument is given, read the cutoff from "Chosen settings" in
`RANKING_STUDY_PLAN.md`. If that table is still empty, stop and tell the user
that phase 1 has to finish first.

Lists, in this order:

1. `ranking_test_patients.txt`: 12 patients, 354 trials
2. `ranking_test_extra_patients.txt`: 34 patients, 2,335 trials

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

## 2. Run in chunks

With a cutoff (replace `50` with it):

```bash
~/trialgpt-venv/bin/python run_parallel.py --patients-file ranking_test_patients.txt --stages match,aggregate,review --min-relevance 50 --max-minutes 8 --no-report
```

With `none`:

```bash
~/trialgpt-venv/bin/python run_parallel.py --patients-file ranking_test_patients.txt --stages match,aggregate --max-minutes 8 --no-report
```

When `ranking_test_patients.txt` reports `status=done remaining_calls=0`, run
the same command with `--patients-file ranking_test_extra_patients.txt`.

Run each as a foreground command with a 10-minute timeout (600000 ms). Read
the final line, `RESULT status=... remaining_calls=N ...`, then save progress
(skip the commit if `git status --porcelain results/` is empty):

```bash
git add results/
git commit -m "Ranking held-out: <test|extra> <status>, <N> calls left"
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
- tokens used today (sum of `tokens=` from the RESULT lines) and how many more
  days the remaining calls need at today's pace
- any errors

Do not give any ranking score. When both lists are finished, say that phase 3
(scoring once, as written in RANKING_STUDY_PLAN.md) can start. Then end your turn.
