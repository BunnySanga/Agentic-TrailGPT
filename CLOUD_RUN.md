# Running the study in Claude Code cloud sessions

Long runs happen in cloud sessions at [claude.ai/code](https://claude.ai/code).
You start a session and type one of the commands below. Claude runs the
scripts in 8-minute chunks, pushes results to the `claude/daily-results` branch
after every chunk, stops when Groq's daily limit is reached, and reports. Type
the same command the next day to continue from that branch.

| Command | What it runs |
|---|---|
| `/criteria-test [variant] [split]` | Criterion test of v1, v2 or v3 against the physician labels |
| `/ranking-baseline` | TrialGPT matching and aggregation (no agents) for the 18 ranking-study patients |
| `/ranking-review` | The Reviewer on the 6 development patients, after the baseline |
| `/ranking-heldout none` | TrialGPT on the 46 held-out patients (phase 2 of `RANKING_STUDY_PLAN.md`; the Reviewer was dropped in phase 1) |
| `/ranking-heldout-review` | After that: the Reviewer once on the 46 held-out patients (ablation, about 2 days) |

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
PKGS='groq==0.10.0 httpx<0.28 nltk==3.8.1 python-dotenv'
if command -v uv >/dev/null; then
  uv venv ~/trialgpt-venv
  uv pip install --python ~/trialgpt-venv/bin/python $PKGS
else
  python3 -m venv ~/trialgpt-venv
  ~/trialgpt-venv/bin/pip install $PKGS
fi
~/trialgpt-venv/bin/python -m nltk.downloader punkt
```

## Criterion test

Type `/criteria-test <variant> <split>`, for example `/criteria-test v3 test`.
It scores an agent version (v1, v2 or v3) against TrialGPT's physician labels
and reports accuracy vs GPT-4 alone, the labels the agents fixed and broke,
and the token cost. `dev` is the fixed 300-criterion development sample and
`test` is the 12 held-out patients. v1, v2 and v3 are finished on both.

## Ranking baseline

Type `/ranking-baseline`. It runs official TrialGPT matching and aggregation
(no agents) for the 6 development patients, then the 12 held-out patients, in
8-minute chunks, and stops at the daily API limit. Type it again the next day
to continue. It reports scores for development patients only; held-out
scores wait until the end of the study.

## Ranking review

Type `/ranking-review` once the baseline has finished the development
patients. It runs the Reviewer with `--min-relevance 0`, so every trial with a
negative label is reviewed once, and then scores the development patients at
several cutoffs and score settings without further API calls.

## Held-out run

Phase 1 of `RANKING_STUDY_PLAN.md` dropped the Reviewer and chose the new
score (penalty 0.25, weight 3), so the held-out run is TrialGPT only. Type
`/ranking-heldout none` every day. It runs TrialGPT on
`ranking_test_patients.txt` (already done) and then
`ranking_test_extra_patients.txt` (34 patients, 2,335 trials, about 11 days),
and reports progress only, never scores.

## Held-out Reviewer run (ablation)

When `/ranking-heldout none` has finished, type `/ranking-heldout-review`
daily until it reports both lists done. It runs the Reviewer once on every
held-out trial with a negative label (about 2.7M tokens, about 2 days), so the
final report can show whether the agent adds anything on 46 patients, not
just 6. It reports progress only, never scores.

## Every day

1. At claude.ai/code start a session on `BunnySanga/Agentic-TrailGPT`
   (branch `main`) with the `TrialGPT Groq` environment, or reply in
   yesterday's session. It resumes from the results branch either way.
2. Type the command, for example `/ranking-baseline`.
3. Come back later and read the summary.

Don't run `run_parallel.py` locally while the cloud is running. Both would
draw on the same keys and write diverging results files.

To look at the results locally:

```bash
git fetch origin && git checkout claude/daily-results
```

## What stops a day's run

- **Daily limit** (the normal case): every key reports a rate limit that
  lasts longer than `KEY_MAX_WAIT_SECONDS`.
- **Done**: no work left for the requested patients or criteria.
- **Safety cap**: 30 chunks (about 4 hours).
