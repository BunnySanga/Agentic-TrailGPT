import unittest

from trialgpt_agents.enhanced_matching import criteria_by_id, enhance_trial_matching


class StubAssertion:
    def analyze_patient_note(self, patient_sentences):
        return {
            "sentence_assertions": [
                {
                    "id": sentence_id,
                    "text": text,
                    "subject": "patient",
                    "polarity": "affirmed",
                    "temporality": "current",
                    "usable_as_patient_evidence": True,
                    "reason": "test evidence",
                }
                for sentence_id, text in patient_sentences.items()
            ],
            "usable_sentence_ids": list(patient_sentences),
        }


class StubClarification:
    def clarify_batch(self, requests, patient_sentences):
        return {
            request["key"]: {
                "triggered": True,
                "trigger_reason": "missing evidence",
                "missing_facts": [],
                "candidate_sentence_ids": [2],
            }
            for request in requests
        }


class StubVerifier:
    def verify_batch(self, requests, patient_sentences):
        return {
            request["key"]: {
                "verdict": "unsupported",
                "support_level": "none",
                "corrected_eligibility": "not enough information",
                "issues": ["Evidence was not sufficient."],
                "needs_human_review": True,
            }
            for request in requests
        }


class EnhancedMatchingTests(unittest.TestCase):
    def test_criteria_numbering_matches_trialgpt_rules(self):
        criteria = "Inclusion Criteria\n\nAge at least 18\n\n\nHas melanoma"
        self.assertEqual(criteria_by_id(criteria), {"0": "Age at least 18", "1": "Has melanoma"})

    def test_preserves_trialgpt_shape_and_emits_review(self):
        trial = {
            "inclusion_criteria": "Inclusion Criteria\n\nAge at least 18",
            "exclusion_criteria": "Exclusion Criteria\n\nActive infection",
        }
        raw = {
            "inclusion": {"0": ["Age is documented.", [0], "included"]},
            "exclusion": {"0": ["No infection evidence.", [], "not excluded"]},
        }
        enhanced, review = enhance_trial_matching(
            raw,
            trial,
            "0. The patient is 55 years old.\n1. No active infection.\n2. Patient denies fever.",
            assertion_agent=StubAssertion(),
            clarification_agent=StubClarification(),
            verifier_agent=StubVerifier(),
        )

        self.assertEqual(enhanced["inclusion"]["0"], ["Age is documented.", [0, 2], "not enough information"])
        self.assertEqual(enhanced["exclusion"]["0"][1], [2])
        self.assertEqual(len(review["criteria"]), 2)
        self.assertEqual(review["criteria"][0]["verifier"]["verdict"], "unsupported")

class ChunkingTests(unittest.TestCase):
    def test_large_trials_split_agent_calls_into_chunks(self):
        class CountingClarification(StubClarification):
            calls = []

            def clarify_batch(self, requests, patient_sentences):
                self.calls.append(len(requests))
                return super().clarify_batch(requests, patient_sentences)

        class CountingVerifier(StubVerifier):
            calls = []

            def verify_batch(self, requests, patient_sentences):
                self.calls.append(len(requests))
                return super().verify_batch(requests, patient_sentences)

        criteria = "\n\n".join(f"Criterion number {index}" for index in range(25))
        trial = {"inclusion_criteria": "Inclusion Criteria\n\n" + criteria, "exclusion_criteria": "Exclusion Criteria"}
        raw = {"inclusion": {str(index): ["reason", [0], "included"] for index in range(25)}, "exclusion": {}}
        clarification, verifier = CountingClarification(), CountingVerifier()
        enhanced, review = enhance_trial_matching(
            raw,
            trial,
            "0. The patient is 60.\n1. Other.\n2. More.",
            assertion_agent=StubAssertion(),
            clarification_agent=clarification,
            verifier_agent=verifier,
        )

        self.assertEqual(clarification.calls, [10, 10, 5])
        self.assertEqual(verifier.calls, [10, 10, 5])
        self.assertEqual(len(enhanced["inclusion"]), 25)
        self.assertEqual(len([item for item in review["criteria"] if "verifier" in item]), 25)


if __name__ == "__main__":
    unittest.main()
