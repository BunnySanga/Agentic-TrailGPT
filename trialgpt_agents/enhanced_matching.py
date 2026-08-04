"""Apply post-matching agents while retaining TrialGPT's result schema."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from trialgpt_assertion.TrialGPT import AssertionAgent as LLMAssertionAgent
from .contracts import coerce_sentence_ids, numbered_patient_sentences
from trialgpt_clarification.TrialGPT import ClarificationAgent as LLMClarificationAgent
from trialgpt_verifier.TrialGPT import VerifierAgent as LLMVerifierAgent


def criteria_by_id(criteria: object) -> dict[str, str]:
    """Mirror TrialGPT's criterion numbering without importing its API client."""
    if not isinstance(criteria, str):
        return {}

    parsed: dict[str, str] = {}
    index = 0
    for criterion in criteria.split("\n\n"):
        criterion = criterion.strip()
        if "inclusion criteria" in criterion.lower() or "exclusion criteria" in criterion.lower():
            continue
        if len(criterion) < 5:
            continue
        parsed[str(index)] = criterion
        index += 1
    return parsed


def _valid_prediction(prediction: object) -> bool:
    return isinstance(prediction, list) and len(prediction) == 3


def _unique_ids(*id_lists: object) -> list[int]:
    result: list[int] = []
    for values in id_lists:
        for sentence_id in coerce_sentence_ids(values):
            if sentence_id not in result:
                result.append(sentence_id)
    return result


def _review_record(
    criterion_type: str,
    criterion_id: str,
    criterion: str,
    prediction: list,
    assertion: dict,
    clarification: dict,
    verifier: dict,
    final_ids: list[int],
    final_label: object,
) -> dict:
    return {
        "criterion_type": criterion_type,
        "criterion_id": criterion_id,
        "criterion": criterion,
        "initial_eligibility": prediction[2],
        "final_eligibility": final_label,
        "assertion": assertion,
        "clarification": clarification,
        "verifier": verifier,
        "final_relevant_sentence_ids": final_ids,
    }


def _batched_llm_enhancement(
    matching_result: Mapping[str, Any],
    trial: Mapping[str, Any],
    patient_sentences: Mapping[int, str],
    assertion_agent: Any,
    clarification_agent: Any,
    verifier_agent: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one Assertion, Clarification, and Verifier call for one trial."""
    enhanced = deepcopy(dict(matching_result))
    review: dict[str, Any] = {"criteria": [], "agent_mode": "llm_batched"}
    work_items: list[dict[str, Any]] = []

    for criterion_type in ("inclusion", "exclusion"):
        predictions = matching_result.get(criterion_type)
        if not isinstance(predictions, Mapping):
            continue
        criteria = criteria_by_id(trial.get(f"{criterion_type}_criteria"))
        for criterion_id, prediction in predictions.items():
            criterion_id = str(criterion_id)
            criterion = criteria.get(criterion_id)
            if criterion is None or not _valid_prediction(prediction):
                review["criteria"].append(
                    {
                        "criterion_type": criterion_type,
                        "criterion_id": criterion_id,
                        "issue": "Criterion text or matching prediction is malformed; kept unchanged.",
                    }
                )
                continue
            work_items.append(
                {
                    "key": f"{criterion_type}:{criterion_id}",
                    "criterion_type": criterion_type,
                    "criterion_id": criterion_id,
                    "criterion": criterion,
                    "prediction": prediction,
                    "cited_ids": coerce_sentence_ids(prediction[1]),
                }
            )

    if not work_items:
        return enhanced, review

    note_assertion = assertion_agent.analyze_patient_note(patient_sentences)
    note_records = {
        int(item["id"]): item
        for item in note_assertion.get("sentence_assertions", [])
        if isinstance(item, Mapping) and str(item.get("id", "")).isdigit()
    }
    usable_note_ids = set(coerce_sentence_ids(note_assertion.get("usable_sentence_ids")))

    clarification_requests = []
    for item in work_items:
        cited_usable_ids = [
            sentence_id for sentence_id in item["cited_ids"] if sentence_id in usable_note_ids
        ]
        assertion = {
            "sentence_assertions": [
                note_records[sentence_id]
                for sentence_id in cited_usable_ids
                if sentence_id in note_records
            ],
            "usable_sentence_ids": cited_usable_ids,
        }
        item["initial_assertion"] = assertion
        clarification_requests.append(
            {
                "key": item["key"],
                "criterion_type": item["criterion_type"],
                "criterion": item["criterion"],
                "initial_label": item["prediction"][2],
                "initial_explanation": item["prediction"][0],
                "current_sentence_ids": cited_usable_ids,
                "assertion": assertion,
            }
        )

    clarifications = clarification_agent.clarify_batch(
        clarification_requests, patient_sentences
    )
    verifier_requests = []
    for item in work_items:
        clarification = clarifications.get(item["key"], {})
        candidate_ids = coerce_sentence_ids(clarification.get("candidate_sentence_ids"))
        final_ids = [
            sentence_id
            for sentence_id in _unique_ids(item["cited_ids"], candidate_ids)
            if sentence_id in usable_note_ids
        ]
        assertion = {
            "sentence_assertions": [
                note_records[sentence_id]
                for sentence_id in final_ids
                if sentence_id in note_records
            ],
            "usable_sentence_ids": final_ids,
        }
        item["final_assertion"] = assertion
        item["clarification"] = clarification
        verifier_requests.append(
            {
                "key": item["key"],
                "criterion_type": item["criterion_type"],
                "criterion": item["criterion"],
                "proposed_explanation": item["prediction"][0],
                "proposed_label": item["prediction"][2],
                "assertion": assertion,
                "clarification": clarification,
            }
        )

    verifications = verifier_agent.verify_batch(verifier_requests, patient_sentences)
    for item in work_items:
        key = item["key"]
        verifier = verifications.get(
            key,
            {
                "verdict": "uncertain",
                "support_level": "none",
                "corrected_eligibility": None,
                "issues": ["Verifier did not return a result for this criterion."],
                "needs_human_review": True,
            },
        )
        prediction = item["prediction"]
        final_ids = item["final_assertion"]["usable_sentence_ids"]
        final_label = verifier.get("corrected_eligibility") or prediction[2]
        enhanced[item["criterion_type"]][item["criterion_id"]] = [
            prediction[0],
            final_ids,
            final_label,
        ]
        review["criteria"].append(
            _review_record(
                item["criterion_type"],
                item["criterion_id"],
                item["criterion"],
                prediction,
                item["final_assertion"],
                item["clarification"],
                verifier,
                final_ids,
                final_label,
            )
        )

    return enhanced, review


def enhance_trial_matching(
    matching_result: Mapping[str, Any],
    trial: Mapping[str, Any],
    numbered_patient: str,
    *,
    model: str | None = None,
    assertion_agent: Any | None = None,
    clarification_agent: Any | None = None,
    verifier_agent: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an aggregation-compatible result plus an auditable review sidecar.

    The enhanced result intentionally keeps TrialGPT's ``[reasoning, ids, label]``
    entries. Review information is emitted separately so existing ranking scripts
    continue to work without changes.
    """
    if not isinstance(matching_result, Mapping):
        return {}, {"error": "matching result is not a JSON object", "criteria": []}

    if any(agent is None for agent in (assertion_agent, clarification_agent, verifier_agent)):
        if not model:
            raise ValueError("model is required when using the LLM-powered agents")
        assertion_agent = assertion_agent or LLMAssertionAgent(model)
        clarification_agent = clarification_agent or LLMClarificationAgent(model)
        verifier_agent = verifier_agent or LLMVerifierAgent(model)
    patient_sentences = numbered_patient_sentences(numbered_patient)
    if not all(
        hasattr(agent, method)
        for agent, method in (
            (assertion_agent, "analyze_patient_note"),
            (clarification_agent, "clarify_batch"),
            (verifier_agent, "verify_batch"),
        )
    ):
        raise TypeError("All enhanced agents must implement the batched LLM interface")
    return _batched_llm_enhancement(
        matching_result,
        trial,
        patient_sentences,
        assertion_agent,
        clarification_agent,
        verifier_agent,
    )
