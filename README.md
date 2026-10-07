# Agentic TrailGPT

Agentic TrailGPT improves the trial ranking of [TrialGPT](https://doi.org/10.1038/s41467-024-53081-z)
(Jin et al., Nature Communications 2024), an LLM pipeline that matches patients
to clinical trials, while keeping the extra cost on top of TrialGPT small.
TrialGPT labels every eligibility rule of a trial for a patient, scores each
trial, and ranks them. It runs unchanged here; we change only the final score.

The original TrialGPT README (setup, datasets, citations) is kept in
[TRIALGPT_README.md](TRIALGPT_README.md).

## Architecture

```text
Patient note
  -> candidate trials (TrialGPT's cached retrieval, dataset/{corpus}/retrieved_trials.json)
  -> TrialGPT matching: a label for every inclusion / exclusion rule     (unchanged)
  -> TrialGPT aggregation: relevance R and eligibility E per trial       (unchanged)
  -> score and rank (agentic_score.py): penalty 0.25 per negative label
     instead of 1, weight 3 on (R+E)/100 instead of 1                    (changed)
  -> ranked trials
```

Why: one "not included" or "excluded" label costs a trial a full point in
TrialGPT's score, and on the development ranking patients 11 of the 13
eligible trials ranked outside the top 10 carried such a label. Two thirds of
GPT-4's rule-level mistakes are in labels the score ignores, so re-checking
labels (v1–v3 below) could barely change the ranking. The new score adds no
LLM calls: our extra cost on top of TrialGPT is zero.

On the 6 development patients NDCG@10 rises from 0.588 to 0.663 and P@10 from
0.183 to 0.233. The settings were chosen there by the rule in
[RANKING_STUDY_PLAN.md](RANKING_STUDY_PLAN.md); the 46 held-out patients are
scored once, at the end.

**Tested and dropped: the Reviewer.** A Reviewer step after aggregation
(`run_parallel.py --stages review`, `trialgpt_agents/targeted_review.py`)
re-checked "not included" / "excluded" labels on relevant trials. On the
development patients it changed no ranking at any cutoff while adding 4.6–22%
tokens: it kept the penalty on 10 of the 11 penalised eligible trials, and most
of its changes were on irrelevant trials. The code and its results are kept.

## Earlier versions (criterion test)

Before the ranking study, the agent stage sat between matching and aggregation
and was tested on TrialGPT's 1,015 physician-labelled rules:

| Version | Agents | What it checks | Held-out accuracy (GPT-4 alone: 91.7%) | Tokens per rule |
|---|---|---|---|---|
| v1 | Assertion, Clarification, Verifier | every rule | 54.2% | 832 |
| v2 | Assertion, Reviewer | labels that are often wrong, and labels with flagged evidence | 86.7% | 208 |
| v3 | Assertion, Reviewer | as v2, but never changes "not enough information" | 92.0% | 152 |

264 rules from 12 held-out patients; see `CRITERIA_TEST_PLAN.md`. The later Reviewer
step reused v3's Reviewer without Assertion, which changed almost no labels.

## Code

| Path | What it is |
|---|---|
| `trialgpt_retrieval/`, `trialgpt_matching/`, `trialgpt_ranking/` | Original TrialGPT stages (LLM calls go through `trialgpt_llm`) |
| `trialgpt_assertion/` | Assertion agent: is each note sentence about the patient, affirmed or negated |
| `trialgpt_clarification/` | Clarification agent (v1): searches the note again for missing facts |
| `trialgpt_verifier/` | Verifier agent (v1): checks each label against its evidence |
| `trialgpt_reviewer/` | Reviewer agent: re-checks labels using the physicians' labelling rules |
| `trialgpt_agents/` | `targeted_review.py` (Reviewer after aggregation, tested and dropped), `enhanced_matching.py` (v1), `reviewed_matching.py` (v2, v3), `contracts.py` (shared helpers) |
| `trialgpt_llm/` | Groq client with a shared pool of API keys, retries, and token tracking |
| `run_parallel.py` | Runs TrialGPT matching and aggregation (and optionally the Reviewer) for many patients at once; resumable |
| `evaluate_criteria.py` | Criterion test: scores v1, v2, v3 against the physician labels |
| `agentic_score.py` | Our trial score: TrialGPT's formula with an adjustable penalty and weight (TrialGPT's own `rank_results.py` is unchanged) |
| `evaluate_rankings.py` | Ranking test: NDCG@10, P@10, token cost and the comparison with TrialGPT |
| `check_groq_keys.py` | Checks that every API key works and shows its rate limits |
| `*_patients.txt` | Fixed patient lists: criterion test; ranking development (6) and held-out (12 + 34) |
| `tests/` | Unit tests (no API calls) |
| `results/` | All outputs; see [results/README.md](results/README.md) |

## Setup

Python 3.11:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-run.txt
.venv/bin/python -m nltk.downloader punkt
cp .env.example .env    # then add your Groq keys to GROQ_API_KEYS
.venv/bin/python check_groq_keys.py
```

`requirements-run.txt` covers everything except the retrieval stage. The full
`requirements.txt` adds the retrieval stack (torch, faiss, MedCPT), which is only
needed to rerun TrialGPT-Retrieval.

The criterion test uses `dataset/criterion_annotations.json` (included), taken from
[ncbi/TrialGPT-Criterion-Annotations](https://huggingface.co/datasets/ncbi/TrialGPT-Criterion-Annotations).

## Running

```bash
# Criterion test (variant v1, v2 or v3; split dev, test or all)
.venv/bin/python evaluate_criteria.py --variant v3 --split test

# Ranking study: TrialGPT, then optionally the Reviewer
.venv/bin/python run_parallel.py --patients-file ranking_dev_patients.txt --stages match,aggregate
.venv/bin/python run_parallel.py --patients-file ranking_dev_patients.txt --stages review --min-relevance 0

# Score: TrialGPT's formula, a chosen setting, or a grid (development patients only)
.venv/bin/python evaluate_rankings.py --patients-file ranking_dev_patients.txt
.venv/bin/python evaluate_rankings.py --patients-file ranking_dev_patients.txt --penalty 0.25 --min-relevance 50
.venv/bin/python evaluate_rankings.py --variants baseline --patients-file ranking_dev_patients.txt --grid

# Tests
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

The ranking study follows [RANKING_STUDY_PLAN.md](RANKING_STUDY_PLAN.md). Long runs are done in Claude Code
cloud sessions; see [CLOUD_RUN.md](CLOUD_RUN.md).
Never run `run_parallel.py` locally while a cloud run is going: both would use
the same keys and write diverging result files.
