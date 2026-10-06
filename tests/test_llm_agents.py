import json
import unittest
from types import SimpleNamespace

from trialgpt_assertion.TrialGPT import AssertionAgent
from trialgpt_clarification.TrialGPT import ClarificationAgent
from trialgpt_agents.enhanced_matching import enhance_trial_matching
from trialgpt_llm.client import parse_json_object
from trialgpt_verifier.TrialGPT import VerifierAgent


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = next(self.responses)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(content)))]
        )


class LlmAgentTests(unittest.TestCase):
    def test_assertion_calls_llm_and_normalizes_sentence_ids(self):
        client = FakeClient(
            [
                {
                    "sentence_assertions": [
                        {
                            "id": 1,
                            "subject": "patient",
                            "polarity": "affirmed",
                            "temporality": "current",
                            "usable_as_patient_evidence": True,
                            "reason": "Direct patient evidence.",
                        }
                    ]
                }
            ]
        )
        result = AssertionAgent("gpt-test", client=client).analyze(
            "Patient has diabetes.", {1: "The patient has diabetes."}, [1, 999]
        )

        self.assertEqual(result["usable_sentence_ids"], [1])
        self.assertEqual(client.calls[0]["model"], "gpt-test")
        self.assertEqual(client.calls[0]["temperature"], 0)

    def test_clarification_uses_full_note_and_filters_existing_ids(self):
        client = FakeClient(
            [
                {
                    "triggered": True,
                    "trigger_reason": "initial_label_not_enough_information",
                    "missing_facts": [
                        {
                            "fact": "recent chemotherapy",
                            "why_needed": "The criterion requires treatment timing.",
                            "queries": ["chemotherapy", "last treatment"],
                            "expected_evidence_type": "treatment date",
                        }
                    ],
                    "candidate_sentence_ids": [1, 2, 99],
                }
            ]
        )
        result = ClarificationAgent("gpt-test", client=client).clarify(
            "Chemotherapy within 6 months.",
            "inclusion",
            "not enough information",
            "Treatment date is not stated.",
            {1: "The patient received chemotherapy.", 2: "The patient is well."},
            [1],
        )

        self.assertEqual(result["candidate_sentence_ids"], [2])
        self.assertIn("The patient received chemotherapy.", client.calls[0]["messages"][1]["content"])

    def test_verifier_preserves_valid_llm_decision(self):
        client = FakeClient(
            [
                {
                    "verdict": "verified",
                    "support_level": "strong",
                    "corrected_eligibility": None,
                    "issues": [],
                    "needs_human_review": False,
                }
            ]
        )
        result = VerifierAgent("gpt-test", client=client).verify(
            "Patient has diabetes.",
            "inclusion",
            "The patient has diabetes.",
            "included",
            {1: "The patient has diabetes."},
            {"sentence_assertions": []},
            {"candidate_sentence_ids": [1]},
        )

        self.assertEqual(result["verdict"], "verified")
        self.assertFalse(result["needs_human_review"])

    def test_batched_pipeline_uses_one_call_per_new_agent(self):
        assertion_client = FakeClient(
            [
                {
                    "sentence_assertions": [
                        {
                            "id": 0,
                            "subject": "patient",
                            "polarity": "affirmed",
                            "temporality": "current",
                            "usable_as_patient_evidence": True,
                            "reason": "Direct evidence.",
                        },
                        {
                            "id": 1,
                            "subject": "patient",
                            "polarity": "affirmed",
                            "temporality": "current",
                            "usable_as_patient_evidence": True,
                            "reason": "Additional evidence.",
                        },
                    ]
                }
            ]
        )
        clarification_client = FakeClient(
            [
                {
                    "results": {
                        "inclusion:0": {
                            "triggered": True,
                            "trigger_reason": "weak_initial_evidence",
                            "missing_facts": [],
                            "candidate_sentence_ids": [1],
                        }
                    }
                }
            ]
        )
        verifier_client = FakeClient(
            [
                {
                    "results": {
                        "inclusion:0": {
                            "verdict": "verified",
                            "support_level": "strong",
                            "corrected_eligibility": "included",
                            "issues": [],
                            "needs_human_review": False,
                        }
                    }
                }
            ]
        )
        raw = {
            "inclusion": {"0": ["The patient has diabetes.", [0], "not enough information"]},
            "exclusion": {},
        }
        trial = {
            "inclusion_criteria": "Inclusion Criteria\n\nPatient must have diabetes.",
            "exclusion_criteria": "Exclusion Criteria",
        }
        enhanced, review = enhance_trial_matching(
            raw,
            trial,
            "0. The patient has diabetes.\n1. The patient is receiving treatment.",
            assertion_agent=AssertionAgent("gpt-test", client=assertion_client),
            clarification_agent=ClarificationAgent("gpt-test", client=clarification_client),
            verifier_agent=VerifierAgent("gpt-test", client=verifier_client),
        )

        self.assertEqual(len(assertion_client.calls), 1)
        self.assertEqual(len(clarification_client.calls), 1)
        self.assertEqual(len(verifier_client.calls), 1)
        self.assertEqual(enhanced["inclusion"]["0"][1], [0, 1])
        self.assertEqual(enhanced["inclusion"]["0"][2], "included")
        self.assertEqual(review["agent_mode"], "llm_batched")

    def test_json_parser_accepts_markdown_fences_and_preamble(self):
        self.assertEqual(parse_json_object("Here is the result:\n```json\n{\"ok\": true}\n```"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
