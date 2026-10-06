"""The Agentic TrailGPT agent: re-check negative labels on relevant trials.

Runs after TrialGPT aggregation. One "not included" or "excluded" label costs
a trial a full point in TrialGPT's ranking score, and on the development
ranking patients most eligible trials ranked outside the top 10 carried such a
label. The Reviewer re-checks only those labels, and only on trials that
TrialGPT's own aggregation scores as relevant (R >= min_relevance). A wrong
negative label on an irrelevant trial only pushes it further down, where it
belongs anyway, so those trials cost nothing extra.

The Reviewer is the v3 Reviewer (trialgpt_reviewer) without the Assertion
agent, which changed almost no labels in the criterion test.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .contracts import coerce_sentence_ids, criteria_by_id, numbered_patient_sentences, request_chunks

NEGATIVE_LABELS = {"inclusion": "not included", "exclusion": "excluded"}
DEFAULT_MIN_RELEVANCE = 50.0


def relevance_score(assessment: object) -> float | None:
    """TrialGPT's relevance score R from an aggregation result, if it has one."""
    if not isinstance(assessment, Mapping):
        return None
    try:
        return float(assessment["relevance_score_R"])
    except (KeyError, TypeError, ValueError):
        return None


def negative_criteria(matching_result: Mapping[str, Any], trial: Mapping[str, Any]) -> list[dict]:
    """Every "not included" / "excluded" prediction whose criterion text is known."""
    found = []
    for criterion_type, negative in NEGATIVE_LABELS.items():
        predictions = matching_result.get(criterion_type)
        if not isinstance(predictions, Mapping):
            continue
        criteria = criteria_by_id(trial.get(f"{criterion_type}_criteria"))
        for criterion_id, prediction in predictions.items():
            criterion_id = str(criterion_id)
            if not (isinstance(prediction, list) and len(prediction) == 3) or prediction[2] != negative:
                continue
            if criterion_id not in criteria:
                continue
            found.append(
                {
                    "key": f"{criterion_type}:{criterion_id}",
                    "criterion_type": criterion_type,
                    "criterion_id": criterion_id,
                    "criterion": criteria[criterion_id],
                    "prediction": prediction,
                }
            )
    return found


def review_negative_labels(
    matching_result: Mapping[str, Any],
    trial: Mapping[str, Any],
    numbered_patient: str,
    relevance: float | None,
    reviewer: Any,
    *,
    min_relevance: float = DEFAULT_MIN_RELEVANCE,
) -> tuple[dict, dict]:
    """Return the matching result with reviewed labels, plus a record of the review.

    The result keeps TrialGPT's shape, so aggregation and ranking read it like
    the original. Trials below ``min_relevance`` or without a negative label
    are returned unchanged and make no API call.
    """
    reviewed = deepcopy(dict(matching_result))
    record: dict[str, Any] = {
        "relevance": relevance,
        "min_relevance": min_relevance,
        "selected": False,
        "criteria": [],
    }
    if relevance is None or relevance < min_relevance:
        return reviewed, record
    items = negative_criteria(matching_result, trial)
    if not items:
        return reviewed, record

    record["selected"] = True
    patient_sentences = numbered_patient_sentences(numbered_patient)
    requests = [
        {
            "key": item["key"],
            "criterion_type": item["criterion_type"],
            "criterion": item["criterion"],
            "original_label": item["prediction"][2],
            "original_explanation": item["prediction"][0],
            "cited_sentence_ids": coerce_sentence_ids(item["prediction"][1]),
        }
        for item in items
    ]
    results: dict[str, dict] = {}
    for chunk in request_chunks(requests):
        results.update(reviewer.review_batch(chunk, patient_sentences))

    for item in items:
        prediction = item["prediction"]
        result = results.get(item["key"]) or {}
        if result.get("changed"):
            reviewed[item["criterion_type"]][item["criterion_id"]] = [
                result.get("reason") or prediction[0],
                result.get("sentence_ids") or [],
                result["label"],
            ]
        record["criteria"].append(
            {
                "criterion_type": item["criterion_type"],
                "criterion_id": item["criterion_id"],
                "criterion": item["criterion"],
                "initial_eligibility": prediction[2],
                "final_eligibility": reviewed[item["criterion_type"]][item["criterion_id"]][2],
                "reviewer": result or None,
            }
        )
    return reviewed, record
