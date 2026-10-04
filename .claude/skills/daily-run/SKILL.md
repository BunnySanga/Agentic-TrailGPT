---
name: daily-run
description: Run today's batch of the TrialGPT pilot study on Groq until the daily API limit is reached, push the results, and report. Use when the user says "start", "continue", "daily run", "run today's batch", or /daily-run.
---

# Daily pilot-study run

Process the patients in `study_patients.txt`, in order, through
matching → Assertion/Clarification/Verifier agents → baseline and enhanced
aggregation with `run_parallel.py`. Keep going until Groq's daily limit stops
the run, push results after every chunk, then report.

## Rules

- Never print, echo, log, or commit API keys. They are in the `GROQ_API_KEYS`
  environment variable. Do not run `env`, `printenv`, or `set`, and do not cat
  files that may hold keys. Scripts here only ever print keys masked (`gsk_…XXXX`).
- Do not edit `study_patients.txt`, prompts, or code during a run. The patient
  list was fixed before any results were seen. If something is broken, stop
  and report instead of patching.
- Results live on the branch `claude/daily-results`. Never push to `main`.
- Use the exact commands below; they match the repo's permission allowlist.

## 1. Prepare

Work from the repository root.

1. If `~/trialgpt-venv/bin/python` does not exist (the environment's setup
   script normally creates it), create it:
   ```bash
   python3 -m venv ~/trialgpt-venv && ~/trialgpt-venv/bin/pip install -q -r requirements-run.txt && ~/trialgpt-venv/bin/python -m nltk.downloader -q punkt
   ```
2. Switch to the results branch so the run resumes from earlier days:
   ```bash
   git fetch origin
   ```
   If `git ls-remote --exit-code --heads origin claude/daily-results` succeeds:
   ```bash
   git checkout -B claude/daily-results origin/claude/daily-results
   git merge --no-edit origin/main
   ```
   Otherwise (first day):
   ```bash
   git checkout -B claude/daily-results origin/main
   ```
3. Check the configuration and keys (prints only masked keys):
   ```bash
   ~/trialgpt-venv/bin/python check_groq_keys.py
   ```
   Expect `Model: openai/gpt-oss-120b`, `Reasoning effort: low`, and every
   key `OK`. If no keys are found, the model differs, or any key fails, stop
   and tell the user which (masked) and why; the fix is in the cloud
   environment's variables (see CLOUD_RUN.md).

## 2. Run in chunks

Repeat this loop. Each chunk stops itself after 8 minutes and saves everything
it finished, so run it as a foreground command with a 10-minute timeout
(600000 ms):

```bash
~/trialgpt-venv/bin/python run_parallel.py --patients-file study_patients.txt --max-minutes 8
```

Read the final line, `RESULT status=... remaining_calls=N ...`, then save
progress:

```bash
git add results/
git commit -m "Daily run: <status>, <N> calls left"
git push -u origin claude/daily-results
```

Skip the commit if `git status --porcelain results/` is empty.

Decide the next step from `status`:

| status | Meaning | Next |
|---|---|---|
| `time_up` | 8 minutes used, work left | Run the next chunk |
| `daily_limit` | Every key is rate limited for a long time | Stop the loop, go to step 3 |
| `done`, `remaining_calls=0` | Study complete | Stop the loop, go to step 3 |
| `done`, `remaining_calls>0` | Pass ended with trial errors | Run one more chunk; if it makes no progress, stop and report the errors |

Stop after 30 chunks (about 4 hours) even if work remains, and say so.

## 3. Report

1. Score the rankings:
   ```bash
   ~/trialgpt-venv/bin/python evaluate_rankings.py
   ```
2. Append today's entry to `results/daily_log.md` (create it with a
   `# Daily run log` heading if missing): date in UTC, chunks run, patients
   completed today, patients complete in total out of 12, remaining calls,
   tokens used today (sum of `tokens=` from the RESULT lines), trial errors,
   and the NDCG@10 / P@10 table.
3. Commit and push:
   ```bash
   git add results/
   git commit -m "Daily run: log for <date>"
   git push -u origin claude/daily-results
   ```
4. Reply to the user with a short summary: patients completed today and in
   total, remaining calls, why the run stopped, the baseline vs enhanced
   NDCG@10 / P@10 table, any errors, and roughly how many more days the
   remaining work needs at today's pace. Then end your turn; the user starts
   the next day's run.
