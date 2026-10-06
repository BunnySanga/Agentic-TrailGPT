"""Agentic TrailGPT's trial score: TrialGPT's formula with an adjustable penalty and weight.

TrialGPT (trialgpt_ranking/rank_results.py, unchanged) scores a trial as

    share of inclusion rules met
    - 1 if any rule is "not included"
    - 1 if any rule is "excluded"
    + (R + E) / 100                 (R, E from TrialGPT aggregation)

One negative label therefore costs a full point, more than anything else in
the score. Here the penalty and the weight on (R + E) / 100 are parameters.
With penalty 1 and weight 1 the score equals TrialGPT's exactly.
"""

from __future__ import annotations

from trialgpt_ranking.rank_results import get_agg_score

EPS = 1e-9  # as in rank_results.py
TRIALGPT_PENALTY = 1.0
TRIALGPT_WEIGHT = 1.0


def matching_score(result: dict, penalty: float = TRIALGPT_PENALTY) -> float:
    """TrialGPT's matching score with an adjustable penalty for negative labels."""
    counts = {"included": 0, "not included": 0, "not enough information": 0, "excluded": 0}
    for criterion_type in ("inclusion", "exclusion"):
        for info in result.get(criterion_type, {}).values():
            if len(info) != 3:
                continue
            label = info[2]
            if criterion_type == "inclusion" and label in ("included", "not included", "not enough information"):
                counts[label] += 1
            elif criterion_type == "exclusion" and label == "excluded":
                counts[label] += 1
    score = counts["included"] / (counts["included"] + counts["not included"] + counts["not enough information"] + EPS)
    if counts["not included"] > 0:
        score -= penalty
    if counts["excluded"] > 0:
        score -= penalty
    return score


def trial_score(
    result: dict, assessment: dict, penalty: float = TRIALGPT_PENALTY, weight: float = TRIALGPT_WEIGHT
) -> float:
    """Score one trial from its matching result and its aggregation assessment."""
    return matching_score(result, penalty) + weight * get_agg_score(assessment)
