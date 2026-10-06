"""Agent versions v2/v3 (criterion test): Assertion + Reviewer on risky labels.

v1 (enhanced_matching.py) sends every criterion through Clarification and the
Verifier. v2 leaves labels that are almost always right alone ("included",
"not excluded" with clean evidence) and asks one Reviewer about the rest.
v3 is v2 without reviewing "not enough information" labels.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from trialgpt_assertion.TrialGPT import AssertionAgent
from trialgpt_reviewer.TrialGPT import ReviewerAgent

from .contracts import coerce_sentence_ids, criteria_by_id, numbered_patient_sentences, request_chunks

# Labels the Reviewer always checks. On development patients GPT-4 was right
# 42% ("not applicable"), 88% ("not enough information"), 62% ("excluded"),
# and 67% ("not included") of the time, versus ~97% for the other two.
REVIEW_LABELS = frozenset({"not applicable", "not enough information", "excluded", "not included"})
# v3: on the 300-criterion dev sample, v2's changes to GPT-4's "not enough
# information" labels were right 5 times out of 27, cancelling its other gains
# (net +1). v3 never reviews them.
V3_REVIEW_LABELS = REVIEW_LABELS - {"not enough information"}
V3_KEEP_LABELS = frozenset({"not enough information"})
AFFIRMATIVE_LABELS = {"included", "excluded"}
# TrialGPT appends this sentence to every note on purpose, so consent and
# compliance criteria can be met. It is an assumption, not a clinical
# statement, so the Assertion agent does not judge it.
CONSENT_SENTENCE_PREFIX = "The patient will provide informed consent"


def consent_sentence_ids(patient_sentences: Mapping[int, str]) -> set[int]:
    return {
        sentence_id
        for sentence_id, text in patient_sentences.items()
        if str(text).startswith(CONSENT_SENTENCE_PREFIX)
    }


def review_trial_matching(
    matching_result: Mapping[str, Any],
    trial: Mapping[str, Any],
    numbered_patient: str,
    *,
    model: str | None = None,
    assertion_agent: Any | None = None,
    reviewer_agent: Any | None = None,
    review_labels: frozenset[str] = REVIEW_LABELS,
    keep_labels: frozenset[str] = frozenset(),
    agent_mode: str = "llm_reviewer_v2",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an aggregation-compatible result plus a review sidecar.

    A criterion is reviewed when its label is in ``review_labels`` or its
    cited evidence is flagged, unless its label is in ``keep_labels``.
    """
    if not isinstance(matching_result, Mapping):
        return {}, {"error": "matching result is not a JSON object", "criteria": []}
    if assertion_agent is None or reviewer_agent is None:
        if not model:
            raise ValueError("model is required when using the LLM-powered agents")
        assertion_agent = assertion_agent or AssertionAgent(model)
        reviewer_agent = reviewer_agent or ReviewerAgent(model)

    patient_sentences = numbered_patient_sentences(numbered_patient)
    enhanced = deepcopy(dict(matching_result))
    review: dict[str, Any] = {"criteria": [], "agent_mode": agent_mode}

    items = []
    for criterion_type in ("inclusion", "exclusion"):
        predictions = matching_result.get(criterion_type)
        if not isinstance(predictions, Mapping):
            continue
        criteria = criteria_by_id(trial.get(f"{criterion_type}_criteria"))
        for criterion_id, prediction in predictions.items():
            criterion_id = str(criterion_id)
            criterion = criteria.get(criterion_id)
            if criterion is None or not (isinstance(prediction, list) and len(prediction) == 3):
                review["criteria"].append(
                    {
                        "criterion_type": criterion_type,
                        "criterion_id": criterion_id,
                        "issue": "Criterion text or matching prediction is malformed; kept unchanged.",
                    }
                )
                continue
            items.append(
                {
                    "key": f"{criterion_type}:{criterion_id}",
                    "criterion_type": criterion_type,
                    "criterion_id": criterion_id,
                    "criterion": criterion,
                    "prediction": prediction,
                    "cited_ids": coerce_sentence_ids(prediction[1]),
                }
            )
    if not items:
        return enhanced, review

    # One note-level assertion pass (cached per patient by the caller).
    consent_ids = consent_sentence_ids(patient_sentences)
    clinical_sentences = {
        sentence_id: text for sentence_id, text in patient_sentences.items() if sentence_id not in consent_ids
    }
    unusable: dict[int, dict] = {}
    negated: set[int] = set()
    if clinical_sentences:
        note_assertion = assertion_agent.analyze_patient_note(clinical_sentences)
        for record in note_assertion.get("sentence_assertions", []):
            sentence_id = int(record["id"])
            if not record.get("usable_as_patient_evidence"):
                unusable[sentence_id] = record
            elif record.get("polarity") == "negated":
                negated.add(sentence_id)

    requests = []
    for item in items:
        label = item["prediction"][2]
        item["unusable_cited"] = [
            {
                "id": sentence_id,
                "subject": unusable[sentence_id].get("subject"),
                "polarity": unusable[sentence_id].get("polarity"),
                "reason": unusable[sentence_id].get("reason"),
            }
            for sentence_id in item["cited_ids"]
            if sentence_id in unusable
        ]
        negated_support = label in AFFIRMATIVE_LABELS and any(
            sentence_id in negated for sentence_id in item["cited_ids"]
        )
        flagged = item["unusable_cited"] or negated_support
        if label not in keep_labels and (label in review_labels or flagged):
            requests.append(
                {
                    "key": item["key"],
                    "criterion_type": item["criterion_type"],
                    "criterion": item["criterion"],
                    "original_label": label,
                    "original_explanation": item["prediction"][0],
                    "cited_sentence_ids": item["cited_ids"],
                    "unusable_cited_sentences": item["unusable_cited"],
                }
            )

    reviews: dict[str, dict] = {}
    for chunk in request_chunks(requests):
        reviews.update(reviewer_agent.review_batch(chunk, patient_sentences))

    for item in items:
        prediction = item["prediction"]
        result = reviews.get(item["key"])
        if result and result.get("changed"):
            enhanced[item["criterion_type"]][item["criterion_id"]] = [
                result.get("reason") or prediction[0],
                result.get("sentence_ids") or [],
                result["label"],
            ]
        review["criteria"].append(
            {
                "criterion_type": item["criterion_type"],
                "criterion_id": item["criterion_id"],
                "criterion": item["criterion"],
                "initial_eligibility": prediction[2],
                "final_eligibility": enhanced[item["criterion_type"]][item["criterion_id"]][2],
                "reviewed": result is not None,
                "reviewer": result,
                "unusable_cited_sentences": item["unusable_cited"],
            }
        )
    return enhanced, review
