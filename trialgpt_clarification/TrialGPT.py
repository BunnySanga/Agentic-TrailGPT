"""LLM-powered patient-note clarification stage for TrialGPT."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from trialgpt_agents.contracts import coerce_sentence_ids
from trialgpt_llm.client import call_json


CLARIFICATION_SYSTEM_PROMPT = """You are the Clarification Agent for clinical trial matching.

The initial matching model may have missed evidence in the patient note. Read
the criterion, initial decision, and the complete numbered patient note. Decide
whether clarification is needed. If it is needed, identify the exact missing
fact and generate targeted queries that can find it in this patient note.

You may select additional sentence IDs only when those sentences provide
possible evidence for the criterion. Do not select family history as patient
diagnosis evidence. Do not invent patient facts, and do not search outside the
provided patient note. Do not make the final eligibility decision.

Return JSON only:
{
  "triggered": true,
  "trigger_reason": "initial_label_not_enough_information",
  "missing_facts": [{
    "fact": "...",
    "why_needed": "...",
    "queries": ["..."],
    "expected_evidence_type": "..."
  }],
  "candidate_sentence_ids": [1, 4]
}

Use triggered=false, an empty missing_facts list, and an empty candidate list
when the initial evidence is sufficient."""

CLARIFICATION_BATCH_SYSTEM_PROMPT = """You are the Clarification Agent for clinical trial matching.

Review every criterion decision in the supplied patient-trial pair. For each
criterion, decide whether the initial evidence is sufficient. When it is not,
identify the missing fact, explain why it is needed, generate targeted queries,
and select possible evidence sentence IDs from the same patient note.

Do not ask the patient or recruiter for interactive input. Do not search for
other trials. Do not invent facts. Family history is not patient diagnosis
evidence. Do not make the final eligibility decision.

Return JSON only in this shape:
{"results": {"inclusion:0": {"triggered": true, "trigger_reason": "...",
"missing_facts": [{"fact": "...", "why_needed": "...", "queries": ["..."],
"expected_evidence_type": "..."}], "candidate_sentence_ids": [1]}}}

Include every supplied criterion key in results. Use empty lists and
triggered=false when no clarification is needed."""


class ClarificationAgent:
    """Use the LLM to identify and search for missing evidence."""

    def __init__(self, model: str, client: Any | None = None):
        self.model = model
        self.client = client

    def clarify(
        self,
        criterion: str,
        criterion_type: str,
        initial_label: str,
        initial_explanation: str,
        patient_sentences: Mapping[int, str],
        current_sentence_ids: object,
    ) -> dict:
        current_ids = set(coerce_sentence_ids(current_sentence_ids))
        note = [
            {"id": int(sentence_id), "text": str(text)}
            for sentence_id, text in sorted(patient_sentences.items(), key=lambda item: int(item[0]))
        ]
        user_prompt = (
            f"Criterion type: {criterion_type}\n"
            f"Criterion: {criterion}\n"
            f"Initial eligibility label: {initial_label}\n"
            f"Initial explanation: {initial_explanation}\n"
            f"Currently cited sentence IDs: {sorted(current_ids)}\n\n"
            "Complete numbered patient note:\n"
            + json.dumps(note, ensure_ascii=True)
            + "\n\nReturn JSON only:"
        )
        result = call_json(
            CLARIFICATION_SYSTEM_PROMPT,
            user_prompt,
            self.model,
            client=self.client,
        )
        return self._normalize(result, patient_sentences, current_ids)

    def clarify_batch(
        self,
        requests: list[Mapping[str, object]],
        patient_sentences: Mapping[int, str],
    ) -> dict[str, dict]:
        """Review all criteria for one patient-trial pair in one LLM call."""
        note = [
            {"id": int(sentence_id), "text": str(text)}
            for sentence_id, text in sorted(patient_sentences.items(), key=lambda item: int(item[0]))
        ]
        request_records = []
        current_ids_by_key: dict[str, set[int]] = {}
        for request in requests:
            key = str(request["key"])
            current_ids = set(coerce_sentence_ids(request.get("current_sentence_ids")))
            current_ids_by_key[key] = current_ids
            request_records.append(
                {
                    "key": key,
                    "criterion_type": request.get("criterion_type"),
                    "criterion": request.get("criterion"),
                    "initial_label": request.get("initial_label"),
                    "initial_explanation": request.get("initial_explanation"),
                    "current_sentence_ids": sorted(current_ids),
                    "assertion": request.get("assertion", {}),
                }
            )
        result = call_json(
            CLARIFICATION_BATCH_SYSTEM_PROMPT,
            "Criteria to review:\n"
            + json.dumps(request_records, ensure_ascii=True)
            + "\n\nNumbered patient note:\n"
            + json.dumps(note, ensure_ascii=True)
            + "\n\nReturn JSON only:",
            self.model,
            client=self.client,
        )
        raw_results = result.get("results", {})
        if not isinstance(raw_results, Mapping):
            raw_results = {}
        normalized: dict[str, dict] = {}
        for request in requests:
            key = str(request["key"])
            value = raw_results.get(key, {})
            if not isinstance(value, Mapping):
                value = {}
            normalized[key] = self._normalize(
                value, patient_sentences, current_ids_by_key[key]
            )
        return normalized

    @staticmethod
    def _normalize(
        result: Mapping[str, object],
        patient_sentences: Mapping[int, str],
        current_ids: set[int],
    ) -> dict:
        raw_facts = result.get("missing_facts", [])
        missing_facts: list[dict] = []
        if isinstance(raw_facts, list):
            for item in raw_facts:
                if not isinstance(item, Mapping):
                    continue
                queries = item.get("queries", [])
                if not isinstance(queries, list):
                    queries = []
                missing_facts.append(
                    {
                        "fact": str(item.get("fact", "")),
                        "why_needed": str(item.get("why_needed", "")),
                        "queries": [str(query) for query in queries if str(query).strip()],
                        "expected_evidence_type": str(
                            item.get("expected_evidence_type", "clinical note evidence")
                        ),
                    }
                )

        candidate_ids = [
            sentence_id
            for sentence_id in coerce_sentence_ids(result.get("candidate_sentence_ids"))
            if sentence_id in patient_sentences and sentence_id not in current_ids
        ]
        return {
            "triggered": result.get("triggered") is True,
            "trigger_reason": (
                str(result.get("trigger_reason"))
                if result.get("trigger_reason") is not None
                else None
            ),
            "missing_facts": missing_facts,
            "candidate_sentence_ids": candidate_ids,
        }


def trialgpt_clarification(
    criterion: str,
    criterion_type: str,
    initial_label: str,
    initial_explanation: str,
    patient_sentences: Mapping[int, str],
    current_sentence_ids: object,
    model: str,
    *,
    client: Any | None = None,
) -> dict:
    """Functional entry point matching the official TrialGPT module style."""
    return ClarificationAgent(model, client=client).clarify(
        criterion,
        criterion_type,
        initial_label,
        initial_explanation,
        patient_sentences,
        current_sentence_ids,
    )
