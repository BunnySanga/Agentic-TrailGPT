# Ranking study plan

Written 2026-10-06, before any Reviewer results and before any ranking score
for the held-out patients.

## Question

Does Agentic TrailGPT rank trials better than TrialGPT, and how much extra
cost does it add on top of TrialGPT?

- **TrialGPT:** matching + aggregation + TrialGPT's score (`rank_results.py`).
- **Agentic TrailGPT:** the same TrialGPT run, then the Reviewer re-checks
  "not included" / "excluded" labels on trials with relevance R ≥ cutoff, and
  the trials are ranked with the rebalanced score.

Both come from one run per patient: the Reviewer reuses TrialGPT's outputs,
so its tokens are the only extra cost.

## Patients (SIGIR, `openai/gpt-oss-120b`)

| List | Patients | Trials | Use |
|---|---|---|---|
| `ranking_dev_patients.txt` | 6 | 258 | Choose the settings (phase 1) |
| `ranking_test_patients.txt` | 12 | 354 | Final test |
| `ranking_test_extra_patients.txt` | 34 | 2,335 | Final test |

Held-out = the 46 patients in the two test lists (2,689 trials). The same rule
picked every list: patients with at least one eligible and one non-eligible
trial. Six SIGIR patients fail it and are left out. The lists are fixed and
not changed after results are seen.

Check group: 14 held-out patients were never used to tune anything (the 12 in
`ranking_test_patients.txt`, plus sigir-20141 and sigir-20156). The other 32
were criterion-test development patients, whose rule labels shaped the
Reviewer prompt; their ranking labels were never used. Two of the 12
(sigir-201415, sigir-201529) were looked at in the 2-patient v1 pilot.

## Phase 1: choose the settings (development patients only)

1. Reviewer on the 6 development patients, once, at cutoff 0 (every trial with
   a negative label): `/ranking-review`. A higher cutoff is simulated exactly
   from this run, because each trial is reviewed on its own.
2. Score with `evaluate_rankings.py --grid` at cutoffs 0, 50 and 70, and without
   the Reviewer. The grid covers penalty 1, 0.75, 0.5, 0.25, 0 and weight 1,
   1.5, 2, 3.
3. Rule, fixed now:
   - For each option (no Reviewer, cutoff 70, cutoff 50, cutoff 0), take its
     best grid row by development NDCG@10. On ties, prefer the row closer to
     TrialGPT's formula (higher penalty, then lower weight).
   - The Reviewer is kept only if its best option beats "no Reviewer" by at
     least 0.01 NDCG@10. Among Reviewer options within 0.005 of the best, take
     the highest cutoff, which is the cheapest.
   - Otherwise the final system is TrialGPT + the new score, with zero extra cost.
4. Write the chosen cutoff, penalty and weight under "Chosen settings" below,
   commit, then start phase 2. No changes after that.

## Phase 2: run the held-out patients

The daily cloud command `/ranking-heldout <cutoff>` runs matching, aggregation
and the Reviewer at the chosen cutoff, first on `ranking_test_patients.txt`,
then on `ranking_test_extra_patients.txt`. With `/ranking-heldout none` it runs
TrialGPT only. It reports progress and tokens, never scores.

Expected cost: about 4,600 tokens per trial for TrialGPT plus the Reviewer's
share, roughly 12M tokens in all, about 12 days at the daily limit.

## Phase 3: score once

When every held-out trial is done, score once:

```bash
python evaluate_rankings.py --variants baseline,reviewed \
  --patients-file ranking_test_patients.txt --patients-file ranking_test_extra_patients.txt \
  --penalty P --weight W --min-relevance T
```

- **Primary:** NDCG@10 of Agentic TrailGPT vs TrialGPT on all 46 held-out
  patients, with the mean per-patient difference, a bootstrap 95% CI (10,000
  resamples, seed 2024), and patients better / same / worse.
- **Secondary:** P@10, the same way; extra tokens per trial (%); the 14-patient
  check group on its own.
- **Ablations**, reported alongside: TrialGPT + new score only; TrialGPT +
  Reviewer at TrialGPT's formula.
- Report the result as it comes out. No tuning after the held-out scores are
  seen.

## Chosen settings

Filled in 2026-10-07 from phase 1 (Reviewer run on the 6 development patients,
results commit 1e1bf44), by the rule above.

| Setting | Value |
|---|---|
| Reviewer cutoff (R ≥) | **none**: Reviewer dropped |
| Penalty per negative label | **0.25** |
| Weight on (R+E)/100 | **3** |
| Development NDCG@10 (TrialGPT formula → chosen) | 0.588 → 0.663 (P@10 0.183 → 0.233) |
| Extra cost on top of TrialGPT | 0 tokens |

Why the Reviewer is dropped: at every cutoff (0, 50, 70) and in 19 of the 20
grid rows, its development NDCG@10 equals the score-only version (in the
other row it is 0.0006 lower), so it never reaches the required +0.01. It
checked 424 labels on 189 trials and changed 31: 21 to "not enough
information", 7 "excluded" → "not excluded", 3 "not included" → "included".
21 of the 27 changed trials are irrelevant to the patient. Of the 11 eligible
trials carrying a −1 penalty it reviewed all 11 and kept the penalty on 10.
Its cost would have been +22% (cutoff 0), +8.4% (50) or +4.6% (70).

The best score-only row is penalty 0.25, weight 3 (0.6631), ahead of penalty
0.75, weight 3 (0.6610) and penalty 0.5, weight 3 (0.6599). It was chosen as
the best of 20 rows on 6 patients, so its development gain (+0.076, 95% CI
+0.025 to +0.132) is optimistic; the held-out run decides.

Phase 2: `/ranking-heldout none` (TrialGPT only; the 12 patients in
`ranking_test_patients.txt` are already done, so it continues with the 34 in
`ranking_test_extra_patients.txt`).

Phase 3 command:

```bash
python evaluate_rankings.py --variants baseline \
  --patients-file ranking_test_patients.txt --patients-file ranking_test_extra_patients.txt \
  --penalty 0.25 --weight 3
```

This reports TrialGPT as published (penalty 1, weight 1) against Agentic
TrailGPT (penalty 0.25, weight 3) on the same TrialGPT outputs.

## Addendum (2026-10-08): the Reviewer on the held-out patients

Added before any held-out ranking score was seen. Six development patients are
too few to judge the agent, so the Reviewer also runs once on all 46 held-out
patients as a pre-specified ablation. The chosen system above does not change.

- **When:** after phase 2 has finished TrialGPT for every held-out trial.
- **How:** `/ranking-heldout-review`, which runs
  `run_parallel.py --stages review --min-relevance 0` on both test lists, so
  every trial with a "not included" or "excluded" label is reviewed once.
  Cutoffs 50 and 70 are scored from the same run, exactly, as in phase 1.
- **Cost:** about 1,000 tokens per trial at cutoff 0 (1,019 on the
  development patients), about 2.7M tokens for 2,689 trials, about 2 days.
- **Reported in phase 3, alongside the primary result:**
  - Reviewer + new score vs new score alone (penalty 0.25, weight 3), at
    cutoffs 0, 50 and 70: does the agent add anything on top of the score?
  - Reviewer at TrialGPT's formula vs TrialGPT: does the agent help on its own?
  - Each with the mean per-patient NDCG@10 and P@10 difference, the bootstrap
    95% CI, patients better / same / worse, and the Reviewer's extra tokens (%).

Phase 3 commands for the ablation:

```bash
python evaluate_rankings.py --variants baseline,reviewed \
  --patients-file ranking_test_patients.txt --patients-file ranking_test_extra_patients.txt
python evaluate_rankings.py --variants baseline,reviewed \
  --patients-file ranking_test_patients.txt --patients-file ranking_test_extra_patients.txt \
  --penalty 0.25 --weight 3 [--min-relevance 50 | --min-relevance 70]
```
