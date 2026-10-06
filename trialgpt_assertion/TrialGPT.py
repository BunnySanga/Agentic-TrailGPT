"""LLM-powered evidence assertion stage for TrialGPT."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from trialgpt_agents.contracts import coerce_sentence_ids
from trialgpt_llm.client import call_json


_SUBJECTS = {"patient", "family", "other", "unclear"}
_POLARITIES = {"affirmed", "negated", "hypothetical", "unclear"}
_TEMPORALITIES = {"current", "historical", "future/planned", "unclear"}


ASSERTION_SYSTEM_PROMPT = """You are the Assertion Agent for clinical trial eligibility matching.

Your task is to inspect candidate evidence sentences selected by another LLM.
For every sentence, determine whether it is evidence about the patient for the
given criterion. Return JSON only.

Classify every sentence with:
- subject: patient | family | other | unclear
- polarity: affirmed | negated | hypothetical | unclear
- temporality: current | historical | future/planned | unclear
- usable_as_patient_evidence: true | false
- reason: one concise explanation

Rules:
- Family history is not evidence that the patient has the condition.
- A negated patient statement is usable evidence about absence, but must not be
  treated as an affirmed diagnosis.
- Hypothetical, planned, screening-only, or unclear statements are not confirmed
  patient facts.
- Historical patient facts can be usable when they are relevant to the criterion.
- Do not invent facts or sentence IDs.

Output exactly:
{"sentence_assertions": [{"id": 0, "text": "...", "subject": "patient", "polarity": "affirmed", "temporality": "current", "usable_as_patient_evidence": true, "reason": "..."}]}"""

PATIENT_NOTE_ASSERTION_SYSTEM_PROMPT = """You are the Assertion Agent for clinical trial eligibility matching.

Inspect every numbered sentence in the patient note. Determine whether each
sentence is a usable assertion about the patient. This is a shared evidence
pass before criterion-level clarification and verification.

Classify every sentence with:
- subject: patient | family | other | unclear
- polarity: affirmed | negated | hypothetical | unclear
- temporality: current | historical | future/planned | unclear
- usable_as_patient_evidence: true | false
- reason: one concise explanation

Rules:
- Family history is not evidence that the patient has the condition.
- Negated patient statements are usable evidence about absence, not presence.
- Hypothetical, planned, screening-only, or unclear statements are not confirmed facts.
- Historical patient facts can be usable evidence.
- Do not invent facts or sentence IDs.

Return JSON only using the exact sentence IDs supplied:
{"sentence_assertions": [{"id": 0, "text": "...", "subject": "patient", "polarity": "affirmed", "temporality": "current", "usable_as_patient_evidence": true, "reason": "..."}]}"""


class AssertionAgent:
    """Call the LLM to validate selected patient evidence."""

    def __init__(self, model: str, client: Any | None = None):
        self.model = model
        self.client = client

    def analyze(
        self,
        criterion: str,
        patient_sentences: Mapping[int, str],
        candidate_sentence_ids: object,
    ) -> dict:
        sentence_ids = [
            sentence_id
            for sentence_id in coerce_sentence_ids(candidate_sentence_ids)
            if sentence_id in patient_sentences
        ]
        sentence_records = [
            {"id": sentence_id, "text": patient_sentences[sentence_id]}
            for sentence_id in sentence_ids
        ]
        user_prompt = (
            "Criterion:\n"
            + criterion
            + "\n\nCandidate evidence sentences:\n"
            + json.dumps(sentence_records, ensure_ascii=True)
            + "\n\nReturn JSON only:"
        )
        result = call_json(
            ASSERTION_SYSTEM_PROMPT,
            user_prompt,
            self.model,
            client=self.client,
        )
        return self._normalize(result, patient_sentences, sentence_ids)

    def analyze_patient_note(self, patient_sentences: Mapping[int, str]) -> dict:
        """Classify the full note once so later stages can reuse assertions."""
        sentence_ids = sorted(int(sentence_id) for sentence_id in patient_sentences)
        sentence_records = [
            {"id": sentence_id, "text": patient_sentences[sentence_id]}
            for sentence_id in sentence_ids
        ]
        result = call_json(
            PATIENT_NOTE_ASSERTION_SYSTEM_PROMPT,
            "Numbered patient note:\n"
            + json.dumps(sentence_records, ensure_ascii=True)
            + "\n\nReturn JSON only:",
            self.model,
            client=self.client,
        )
        return self._normalize(result, patient_sentences, sentence_ids)

    @staticmethod
    def _normalize(
        result: Mapping[str, object],
        patient_sentences: Mapping[int, str],
        candidate_ids: list[int],
    ) -> dict:
        raw_assertions = result.get("sentence_assertions", [])
        by_id: dict[int, dict] = {}
        if isinstance(raw_assertions, list):
            for item in raw_assertions:
                if not isinstance(item, Mapping):
                    continue
                try:
                    sentence_id = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                if sentence_id not in candidate_ids or sentence_id in by_id:
                    continue
                raw_subject = item.get("subject")
                raw_polarity = item.get("polarity")
                raw_temporality = item.get("temporality")
                subject = raw_subject if isinstance(raw_subject, str) else None
                polarity = raw_polarity if isinstance(raw_polarity, str) else None
                temporality = raw_temporality if isinstance(raw_temporality, str) else None
                usable = item.get("usable_as_patient_evidence")
                by_id[sentence_id] = {
                    "id": sentence_id,
                    "text": patient_sentences[sentence_id],
                    "subject": subject if subject in _SUBJECTS else "unclear",
                    "polarity": polarity if polarity in _POLARITIES else "unclear",
                    "temporality": temporality if temporality in _TEMPORALITIES else "unclear",
                    "usable_as_patient_evidence": usable is True,
                    "reason": str(item.get("reason", "The assertion requires review.")),
                }

        # Missing model entries are kept visible and unusable instead of silently
        # allowing unreviewed evidence to flow into the verifier.
        assertions = [
            by_id.get(
                sentence_id,
                {
                    "id": sentence_id,
                    "text": patient_sentences[sentence_id],
                    "subject": "unclear",
                    "polarity": "unclear",
                    "temporality": "unclear",
                    "usable_as_patient_evidence": False,
                    "reason": "The LLM did not return an assertion for this sentence.",
                },
            )
            for sentence_id in candidate_ids
        ]
        return {
            "sentence_assertions": assertions,
            "usable_sentence_ids": [
                item["id"] for item in assertions if item["usable_as_patient_evidence"]
            ],
        }


def trialgpt_assertion(
    criterion: str,
    patient_sentences: Mapping[int, str],
    candidate_sentence_ids: object,
    model: str,
    *,
    client: Any | None = None,
) -> dict:
    """Functional entry point matching the official TrialGPT module style."""
    return AssertionAgent(model, client=client).analyze(
        criterion, patient_sentences, candidate_sentence_ids
    )


class CachedNoteAssertion:
    """Classify a patient's note once and reuse it for every trial.

    The note-level assertion depends only on the patient note, so repeating it
    per trial costs one API call per trial for an identical answer.
    """

    def __init__(self, agent: AssertionAgent):
        self._agent = agent
        self._result = None

    def analyze_patient_note(self, patient_sentences):
        if self._result is None:
            self._result = self._agent.analyze_patient_note(patient_sentences)
        return self._result
