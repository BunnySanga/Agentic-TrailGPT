# Running the pilot study in Claude Code cloud sessions

Each day you start a cloud session at [claude.ai/code](https://claude.ai/code)
and type `/daily-run`. Claude runs `run_parallel.py` on `study_patients.txt` in
8-minute chunks, pushes results to the `claude/daily-results` branch after
every chunk, stops when Groq's daily limit is reached, and reports. The next
day it resumes from that branch.

## One-time setup

### 1. Connect GitHub

At claude.ai/code, connect your GitHub account and make sure the **Claude
GitHub App** is installed on `BunnySanga/Agentic-TrailGPT`. Sessions need it to
push results.

### 2. Create a cloud environment

At claude.ai/code, open the environment selector and create a new environment
named `TrialGPT Groq`:

**Network access:** select **Custom**. In **Allowed domains** enter:

```text
api.groq.com
```

and check **Also include default list of common package managers** (needed to
install Python packages).

**Environment variables** (`.env` format):

```text
GROQ_API_KEYS=<your six keys, comma-separated, no spaces>
MODEL=openai/gpt-oss-120b
GROQ_REASONING_EFFORT=low
MAX_WORKERS=3
KEY_MAX_WAIT_SECONDS=900
```

To copy the keys line without displaying it, run this in `TrialGPT/` and paste:

```bash
grep '^GROQ_API_KEYS=' .env | pbcopy
```

The keys go in environment variables rather than **API credentials** because
API credentials attach a single key per host, which would defeat the six-key
rotation. Anyone who uses this environment can read its variables, so keep it
to yourself.

**Setup script:**

```bash
#!/bin/bash
set -euo pipefail
PKGS='groq==0.10.0 httpx<0.28 nltk==3.8.1 python-dotenv tqdm==4.65.0'
if command -v uv >/dev/null; then
  uv venv ~/trialgpt-venv
  uv pip install --python ~/trialgpt-venv/bin/python $PKGS
else
  python3 -m venv ~/trialgpt-venv
  ~/trialgpt-venv/bin/pip install $PKGS
fi
~/trialgpt-venv/bin/python -m nltk.downloader punkt
```

## Criterion-level test (run this first)

Start a session as below and type `/criteria-test` (same as `/criteria-test v1 dev`).
It scores the agents against TrialGPT's physician labels on a fixed
300-criterion development sample and reports accuracy vs GPT-4's 87.3%, what
the agents fixed and broke, and the token cost. `/criteria-test v1 test` scores
the held-out patients; run that only at the end.

## Ranking baseline

Type `/ranking-baseline`. It runs official TrialGPT matching and aggregation
(no agents) for the 6 development patients, then the 12 held-out patients, in
8-minute chunks, and stops at the daily API limit. Type it again the next day
to continue. It reports scores for development patients only; held-out
scores wait until the end of the study.

## Every day (ranking study)

1. At claude.ai/code start a session on `BunnySanga/Agentic-TrailGPT`
   (branch `main`) with the `TrialGPT Groq` environment. Or reply in
   yesterday's session; it resumes from the results branch either way.
2. Type `/daily-run`.
3. Come back later and read the summary. Each day is also appended to
   `results/daily_log.md` on the `claude/daily-results` branch.

Don't run `run_parallel.py` locally while the cloud is running. Both would
draw on the same keys and write diverging results files.

To look at the results locally:

```bash
git fetch origin && git checkout claude/daily-results
```

## What stops a day's run

- **Daily limit** (the normal case): every key reports a rate limit that
  lasts longer than `KEY_MAX_WAIT_SECONDS`.
- **Study complete**: all 12 patients have baseline and enhanced results.
- **Safety cap**: 30 chunks (about 4 hours).
