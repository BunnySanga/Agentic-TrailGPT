"""LLM-powered verification stage for TrialGPT matching decisions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from trialgpt_agents.contracts import ALLOWED_LABELS, fallback_label
from trialgpt_llm.client import call_json


_VERDICTS = {"verified", "unsupported", "contradicted", "uncertain"}
_SUPPORT_LEVELS = {"strong", "partial", "weak", "none"}


VERIFIER_SYSTEM_PROMPT = """You are the Verifier Agent for clinical trial eligibility matching.

Check whether the proposed criterion-level label and explanation are supported
by the patient evidence and Assertion/Clarification outputs. Return JSON only.

Rules:
- Verify only against the provided patient note and agent outputs.
- Family history is not patient evidence.
- A negated statement supports absence, not presence.
- Planned, hypothetical, screening-only, or unclear evidence cannot support a
  definitive eligibility label.
- Do not invent medical facts.
- If the label is unsupported or contradicted, give the most defensible valid
  TrialGPT label as corrected_eligibility. Use `not enough information` when
  the evidence does not establish the decision.
- Set needs_human_review=true when evidence is conflicting, ambiguous, or weak.

Return exactly:
{
  "verdict": "verified|unsupported|contradicted|uncertain",
  "support_level": "strong|partial|weak|none",
  "corrected_eligibility": "valid label or null",
  "issues": ["short issue"],
  "needs_human_review": true
}"""

VERIFIER_BATCH_SYSTEM_PROMPT = """You are the Verifier Agent for clinical trial eligibility matching.

Verify every criterion-level decision in the supplied patient-trial pair. Check
the explanation, selected evidence, Assertion output, Clarification output,
and proposed eligibility label. Return one verdict per criterion key.

Use only the supplied patient note and outputs. Family history is not patient
evidence. Negated evidence supports absence, not presence. Planned,
hypothetical, screening-only, or unclear evidence cannot support a definitive
label. Do not invent medical facts. Use a valid TrialGPT label when correcting
an output and use `not enough information` when the evidence is insufficient.

Return JSON only:
{"results": {"inclusion:0": {"verdict": "verified|unsupported|contradicted|uncertain",
"support_level": "strong|partial|weak|none", "corrected_eligibility": null,
"issues": [], "needs_human_review": false}}}"""


class VerifierAgent:
    """Use an Azure deployment to verify the complete criterion decision."""

    def __init__(self, model: str, client: Any | None = None):
        self.model = model
        self.client = client

    def verify(
        self,
        criterion: str,
        criterion_type: str,
        proposed_explanation: str,
        proposed_label: object,
        patient_sentences: Mapping[int, str],
        assertion_result: Mapping[str, object],
        clarification_result: Mapping[str, object],
    ) -> dict:
        evidence = {
            "patient_sentences": [
                {"id": int(sentence_id), "text": str(text)}
                for sentence_id, text in sorted(
                    patient_sentences.items(), key=lambda item: int(item[0])
                )
            ],
            "assertion": assertion_result,
            "clarification": clarification_result,
        }
        user_prompt = (
            f"Criterion type: {criterion_type}\n"
            f"Criterion: {criterion}\n"
            f"Proposed explanation: {proposed_explanation}\n"
            f"Proposed eligibility label: {proposed_label}\n\n"
            "Patient evidence and preceding-agent outputs:\n"
            + json.dumps(evidence, ensure_ascii=True)
            + "\n\nReturn JSON only:"
        )
        result = call_json(
            VERIFIER_SYSTEM_PROMPT,
            user_prompt,
            self.model,
            client=self.client,
        )
        return self._normalize(result, criterion_type)

    def verify_batch(
        self,
        requests: list[Mapping[str, object]],
        patient_sentences: Mapping[int, str],
    ) -> dict[str, dict]:
        """Verify all criteria for one patient-trial pair in one LLM call."""
        note = [
            {"id": int(sentence_id), "text": str(text)}
            for sentence_id, text in sorted(patient_sentences.items(), key=lambda item: int(item[0]))
        ]
        request_records = []
        types_by_key: dict[str, str] = {}
        for request in requests:
            key = str(request["key"])
            criterion_type = str(request["criterion_type"])
            types_by_key[key] = criterion_type
            request_records.append(
                {
                    "key": key,
                    "criterion_type": criterion_type,
                    "criterion": request.get("criterion"),
                    "proposed_explanation": request.get("proposed_explanation"),
                    "proposed_label": request.get("proposed_label"),
                    "assertion": request.get("assertion", {}),
                    "clarification": request.get("clarification", {}),
                }
            )
        result = call_json(
            VERIFIER_BATCH_SYSTEM_PROMPT,
            "Criterion decisions to verify:\n"
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
            normalized[key] = self._normalize(value, types_by_key[key])
        return normalized

    @staticmethod
    def _normalize(result: Mapping[str, object], criterion_type: str) -> dict:
        valid_labels = ALLOWED_LABELS.get(criterion_type, set())
        corrected = result.get("corrected_eligibility")
        issues = result.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)] if issues else []
        issues = [str(issue) for issue in issues]
        needs_review = result.get("needs_human_review") is True

        if corrected is not None and (
            not isinstance(corrected, str) or corrected not in valid_labels
        ):
            corrected = fallback_label(criterion_type)
            issues.append("The verifier returned an invalid corrected label; conservative fallback applied.")
            needs_review = True

        verdict = result.get("verdict")
        support_level = result.get("support_level")
        if not isinstance(verdict, str) or verdict not in _VERDICTS:
            verdict = "uncertain"
            needs_review = True
            issues.append("The verifier returned an invalid verdict.")
        if not isinstance(support_level, str) or support_level not in _SUPPORT_LEVELS:
            support_level = "none"
            needs_review = True
            issues.append("The verifier returned an invalid support level.")

        return {
            "verdict": verdict,
            "support_level": support_level,
            "corrected_eligibility": corrected,
            "issues": issues,
            "needs_human_review": needs_review,
        }


def trialgpt_verifier(
    criterion: str,
    criterion_type: str,
    proposed_explanation: str,
    proposed_label: object,
    patient_sentences: Mapping[int, str],
    assertion_result: Mapping[str, object],
    clarification_result: Mapping[str, object],
    model: str,
    *,
    client: Any | None = None,
) -> dict:
    """Functional entry point matching the official TrialGPT module style."""
    return VerifierAgent(model, client=client).verify(
        criterion,
        criterion_type,
        proposed_explanation,
        proposed_label,
        patient_sentences,
        assertion_result,
        clarification_result,
    )
