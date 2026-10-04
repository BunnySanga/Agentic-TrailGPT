"""LLM-powered Reviewer: corrects risky TrialGPT criterion labels (agent variant v2).

The v1 pipeline (Clarification + Verifier) changed correct labels to
"not enough information" far more often than it fixed mistakes. On the
development patients of TrialGPT's physician annotations, GPT-4's
"not excluded" and "included" labels were ~97% correct, while
"not applicable" was right only 42% of the time (mostly physicians said
"not excluded" for exclusion conditions the note never mentions).

The Reviewer therefore sees only risky labels and applies TrialGPT's label
definitions as the physicians used them, keeping the original label when in
doubt. The rules below were derived from development patients only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from trialgpt_agents.contracts import coerce_sentence_ids, is_valid_label
from trialgpt_llm.client import call_json


REVIEWER_SYSTEM_PROMPT = """You are the Reviewer for TrialGPT clinical trial eligibility labels.

For one patient and one trial you receive criteria that a matching model
already labeled, with its explanation and cited sentence IDs, plus notes on
cited sentences that are not usable patient evidence. Decide the correct label
for each criterion using the definitions below. Change a label only when the
original clearly breaks a definition. If you are unsure, keep the original.

Label definitions:
- "not applicable": only when the patient cannot belong to the population the
  criterion is about (for example a pregnancy criterion for a man or a child,
  a criterion only for children when the patient is an adult), or the
  criterion is about trial logistics or research procedures rather than the
  patient (for example prior enrollment in this study). A condition the
  patient simply does not have is NOT "not applicable".
- Exclusion criteria (a condition, history, treatment, or event that would
  exclude the patient):
  - "excluded": the note shows the patient has it.
  - "not excluded": the note shows the patient does not have it, OR it is a
    medically important fact (a diagnosis, disease history, major treatment,
    surgery, or serious event) that a good patient note would mention and
    the note does not mention it. Assume such unmentioned facts are absent.
  - "not enough information": it depends on a specific detail a good note
    could reasonably leave out (a lab value or threshold, a test result, a
    score, an exact date or duration, a measurement) and nothing in the note
    allows a reasonable inference.
- Inclusion criteria (something the patient must have or be):
  - "included": the note shows the patient meets it, or it follows clearly
    from the note (age, sex, a diagnosis implied by the described findings).
  - "not included": the note shows the patient does not meet it, or it
    requires a medically important condition a good note would mention and
    the note does not mention it.
  - "not enough information": same rule as for exclusion criteria.
- Consent, willingness, and protocol-compliance criteria are satisfied by the
  note's sentence that the patient will provide informed consent and comply
  with the trial protocol: an inclusion criterion of this kind is "included",
  and an exclusion criterion about being unwilling or unable to comply is
  "not excluded".
- Family history, other people's conditions, and hypothetical or
  differential diagnoses are not evidence that the patient has a condition.
- Use only the patient note. Do not invent facts.

Return JSON only, one entry per supplied key:
{"results": {"exclusion:0": {"label": "not excluded", "changed": true,
"reason": "one short sentence", "sentence_ids": [1]}}}"""


class ReviewerAgent:
    """Review risky criterion labels for one patient-trial pair."""

    def __init__(self, model: str, client: Any | None = None):
        self.model = model
        self.client = client

    def review_batch(
        self,
        requests: list[Mapping[str, object]],
        patient_sentences: Mapping[int, str],
    ) -> dict[str, dict]:
        """Review a chunk of criteria in one LLM call; keyed by request key."""
        note = [
            {"id": int(sentence_id), "text": str(text)}
            for sentence_id, text in sorted(patient_sentences.items(), key=lambda item: int(item[0]))
        ]
        records = [
            {
                "key": request["key"],
                "criterion_type": request["criterion_type"],
                "criterion": request["criterion"],
                "original_label": request["original_label"],
                "original_explanation": request["original_explanation"],
                "cited_sentence_ids": request.get("cited_sentence_ids", []),
                "unusable_cited_sentences": request.get("unusable_cited_sentences", []),
            }
            for request in requests
        ]
        result = call_json(
            REVIEWER_SYSTEM_PROMPT,
            "Criteria to review:\n"
            + json.dumps(records, ensure_ascii=True)
            + "\n\nNumbered patient note:\n"
            + json.dumps(note, ensure_ascii=True)
            + "\n\nReturn JSON only:",
            self.model,
            client=self.client,
        )
        raw_results = result.get("results", {})
        if not isinstance(raw_results, Mapping):
            raw_results = {}
        return {
            str(request["key"]): self._normalize(
                raw_results.get(str(request["key"])), request, patient_sentences
            )
            for request in requests
        }

    @staticmethod
    def _normalize(
        result: object,
        request: Mapping[str, object],
        patient_sentences: Mapping[int, str],
    ) -> dict:
        """Accept a valid label; otherwise keep the original label unchanged."""
        original = request["original_label"]
        criterion_type = str(request["criterion_type"])
        if not isinstance(result, Mapping):
            return {"label": original, "changed": False, "reason": "No review returned; original kept.",
                    "sentence_ids": None, "valid": False}
        label = result.get("label")
        if not is_valid_label(criterion_type, label):
            return {"label": original, "changed": False,
                    "reason": f"Invalid label {label!r} returned; original kept.",
                    "sentence_ids": None, "valid": False}
        sentence_ids = [
            sentence_id
            for sentence_id in coerce_sentence_ids(result.get("sentence_ids"))
            if sentence_id in patient_sentences
        ]
        return {
            "label": label,
            "changed": label != original,
            "reason": str(result.get("reason", "")),
            "sentence_ids": sentence_ids,
            "valid": True,
        }
