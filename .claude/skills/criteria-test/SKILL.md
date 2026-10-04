---
name: criteria-test
description: Score an agent variant against TrialGPT's physician criterion annotations with evaluate_criteria.py, push the results, and report. Use when the user says "criteria test", "run the criterion evaluation", or /criteria-test [variant] [split].
---

# Criterion-level agent test

Runs the agents on GPT-4's published TrialGPT predictions for the physician-
annotated criteria in `dataset/criterion_annotations.json` and scores the
final labels against the physicians. GPT-4 alone scores 87.3%.

Arguments: `[variant] [split]`, default `v1 dev`.
- `dev` means the fixed 300-criterion development sample: `--split dev --sample 300`.
- `test` means the held-out patients in `criteria_test_patients.txt`: `--split test`.
  Only run `test` when the user asks for it by name.

## Rules

- Never print, echo, log, or commit API keys (`GROQ_API_KEYS`). Do not run
  `env`, `printenv`, or `set`. Scripts here print keys only masked.
- Do not edit prompts, code, `criteria_test_patients.txt`, or the dataset
  during a run. If something is broken, stop and report.
- Results go to the branch `claude/daily-results`. Never push to `main`.

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

For `dev` (replace `v1` with the requested variant):

```bash
~/trialgpt-venv/bin/python evaluate_criteria.py --variant v1 --split dev --sample 300 --max-minutes 8
```

For `test`:

```bash
~/trialgpt-venv/bin/python evaluate_criteria.py --variant v1 --split test --max-minutes 8
```

Run it as a foreground command with a 10-minute timeout (600000 ms). Read the
final line, `RESULT status=... remaining_pairs=N ...`, then save progress
(skip the commit if `git status --porcelain results/` is empty):

```bash
git add results/
git commit -m "Criteria test: <variant> <split>, <status>, <N> pairs left"
git push -u origin claude/daily-results
```

| status | Next |
|---|---|
| `time_up` | Run the same command again |
| `daily_limit` | Stop; tell the user to run `/criteria-test` again tomorrow |
| `done`, `remaining_pairs=0` | Finished; go to step 3 |
| `done`, `remaining_pairs>0` | Pairs had errors; run once more, and if nothing changes, report the errors |

Stop after 20 chunks even if work remains, and say so.

## 3. Report

The last run prints the full report and saves
`results/criteria_eval_<variant>_<split>..._openai_gpt-oss-120b.json`.
Commit and push it, then reply to the user with:

- accuracy: GPT-4 baseline vs with agents, and the McNemar p-value
- labels changed, GPT-4 mistakes fixed, correct labels broken, net
- the main kinds of changes (GPT-4 label -> agent label, right/total)
- which GPT-4 mistake types the agents fixed
- evidence-sentence precision/recall vs physicians
- agent cost: tokens per criterion

Explain the result in plain words, then end your turn.
