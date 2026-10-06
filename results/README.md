# Results

Every script writes here. Cloud runs push their results to the
`claude/daily-results` branch, so the newest files are there:

```bash
git fetch origin && git checkout claude/daily-results
```

The scripts resume from these files, so don't rename or move the current ones.

## Criterion test (`evaluate_criteria.py`)

| File | Contents |
|---|---|
| `criteria_<variant>_openai_gpt-oss-120b.json` | Agent output for every annotated patient–trial pair (v1, v2, v3) |
| `criteria_eval_<variant>_<split>_openai_gpt-oss-120b.json` | Scores: accuracy vs the physicians, labels fixed and broken, McNemar p, tokens per criterion |

`<split>` is `dev_sample300` (development sample, 301 criteria), `test`
(12 held-out patients, 264 criteria) or `all`.

## Ranking study (`run_parallel.py`, `evaluate_rankings.py`)

| File | Contents |
|---|---|
| `matching_results_sigir_openai_gpt-oss-120b.json` | TrialGPT matching: a label for every rule of every trial |
| `aggregation_results_sigir_openai_gpt-oss-120b_baseline.json` | TrialGPT aggregation: relevance R and eligibility E per trial |
| `matching_results_sigir_openai_gpt-oss-120b_reviewed.json` | Matching after the Reviewer (same shape as TrialGPT's) |
| `review_sigir_openai_gpt-oss-120b.json` | Per trial: R, the cutoff used, whether it was reviewed, and each label checked |
| `usage_sigir_openai_gpt-oss-120b.json` | API calls and tokens per stage (`match`, `agg-baseline`, `review`), patient and trial |
| `evaluation_sigir_openai_gpt-oss-120b_<variants>_<patients>[_p<penalty>_w<weight>][_r<cutoff>][_grid].json` | NDCG@10 and P@10 per patient and on average, plus token cost |

Variants: `baseline` is TrialGPT alone; `reviewed` is TrialGPT after the
Reviewer. Without `_p.._w..` in the name the score is TrialGPT's own formula.

## Archive

Earlier runs, kept for reference. No script reads them.

| Folder | Contents |
|---|---|
| `archive/qwen_pilot/` | First pilot with qwen/qwen3.8-27b and the v1 agents (the mid-review results) |
| `archive/v1_ranking_pilot/` | gpt-oss-120b, TrialGPT vs v1 on 2 patients (sigir-201415, sigir-201529): NDCG@10 0.539 vs 0.531, 5,512 vs 17,736 tokens per trial |
