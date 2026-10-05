import unittest

from trialgpt_agents.reviewed_matching import V3_KEEP_LABELS, V3_REVIEW_LABELS, review_trial_matching
from trialgpt_reviewer.TrialGPT import ReviewerAgent

NOTE = (
    "0. A 60-year-old man with chest pain.\n"
    "1. His father has diabetes.\n"
    "2. He has no history of stroke.\n"
    "3. The patient will provide informed consent, and will comply with the trial protocol."
)


class StubAssertion:
    def __init__(self):
        self.seen = None

    def analyze_patient_note(self, patient_sentences):
        self.seen = dict(patient_sentences)
        records = [
            {"id": 0, "subject": "patient", "polarity": "affirmed", "usable_as_patient_evidence": True},
            {"id": 1, "subject": "family", "polarity": "affirmed", "usable_as_patient_evidence": False,
             "reason": "Father, not patient."},
            {"id": 2, "subject": "patient", "polarity": "negated", "usable_as_patient_evidence": True},
        ]
        return {"sentence_assertions": records}


class StubReviewer:
    def __init__(self, decisions):
        self.decisions = decisions
        self.requests = []

    def review_batch(self, requests, patient_sentences):
        self.requests.extend(requests)
        results = {}
        for request in requests:
            label = self.decisions.get(request["key"], request["original_label"])
            results[request["key"]] = {
                "label": label,
                "changed": label != request["original_label"],
                "reason": "reviewed",
                "sentence_ids": [2],
                "valid": True,
            }
        return results


TRIAL = {
    "inclusion_criteria": "Inclusion Criteria\n\nMale patients\n\nDiabetes mellitus\n\nHistory of stroke",
    "exclusion_criteria": "Exclusion Criteria\n\nPregnancy\n\nActive cancer",
}
MATCHING = {
    "inclusion": {
        "0": ["The patient is a man.", [0], "included"],
        "1": ["Father has diabetes.", [1], "included"],
        "2": ["Stroke mentioned.", [2], "included"],
    },
    "exclusion": {
        "0": ["Patient is male.", [0], "not applicable"],
        "1": ["No cancer mentioned.", [], "not excluded"],
    },
}


class ReviewedMatchingTests(unittest.TestCase):
    def run_pipeline(self, decisions=None):
        assertion, reviewer = StubAssertion(), StubReviewer(decisions or {})
        enhanced, review = review_trial_matching(
            MATCHING, TRIAL, NOTE, assertion_agent=assertion, reviewer_agent=reviewer
        )
        return assertion, reviewer, enhanced, review

    def test_only_risky_labels_are_reviewed(self):
        _, reviewer, _, _ = self.run_pipeline()
        keys = {request["key"] for request in reviewer.requests}
        # inclusion:0 is a clean "included"; exclusion:1 is a clean "not excluded".
        # inclusion:1 cites a family-history sentence, inclusion:2 cites a negated
        # sentence for an affirmative label, exclusion:0 is "not applicable".
        self.assertEqual(keys, {"inclusion:1", "inclusion:2", "exclusion:0"})
        family = next(request for request in reviewer.requests if request["key"] == "inclusion:1")
        self.assertEqual(family["unusable_cited_sentences"][0]["subject"], "family")

    def test_consent_sentence_is_not_sent_to_assertion(self):
        assertion, _, _, _ = self.run_pipeline()
        self.assertNotIn(3, assertion.seen)
        self.assertIn(2, assertion.seen)

    def test_changes_are_applied_and_unreviewed_labels_kept(self):
        _, _, enhanced, review = self.run_pipeline({"inclusion:2": "not included"})
        self.assertEqual(enhanced["inclusion"]["2"], ["reviewed", [2], "not included"])
        self.assertEqual(enhanced["inclusion"]["0"], MATCHING["inclusion"]["0"])
        self.assertEqual(enhanced["exclusion"]["0"], MATCHING["exclusion"]["0"])  # reviewed, kept
        self.assertEqual(review["agent_mode"], "llm_reviewer_v2")
        reviewed = {item["criterion_id"] + item["criterion_type"]: item["reviewed"] for item in review["criteria"]}
        self.assertFalse(reviewed["1exclusion"])


class V3Tests(unittest.TestCase):
    def test_not_enough_information_is_never_reviewed_even_with_flagged_evidence(self):
        matching = {
            "inclusion": {"1": ["Father has diabetes.", [1], "not enough information"],
                          "2": ["Stroke mentioned.", [2], "included"]},
            "exclusion": {"0": ["Patient is male.", [0], "not applicable"]},
        }
        trial = dict(TRIAL, inclusion_criteria="Inclusion Criteria\n\nMale patients\n\nDiabetes mellitus\n\nHistory of stroke")
        reviewer = StubReviewer({})
        review_trial_matching(
            matching, trial, NOTE, assertion_agent=StubAssertion(), reviewer_agent=reviewer,
            review_labels=V3_REVIEW_LABELS, keep_labels=V3_KEEP_LABELS, agent_mode="llm_reviewer_v3",
        )
        self.assertEqual({request["key"] for request in reviewer.requests}, {"inclusion:2", "exclusion:0"})


class ReviewerNormalizeTests(unittest.TestCase):
    request = {"key": "exclusion:0", "criterion_type": "exclusion", "original_label": "not applicable"}

    def test_invalid_label_keeps_original(self):
        result = ReviewerAgent._normalize({"label": "included"}, self.request, {0: "x"})
        self.assertEqual((result["label"], result["changed"], result["valid"]), ("not applicable", False, False))

    def test_missing_result_keeps_original(self):
        result = ReviewerAgent._normalize(None, self.request, {0: "x"})
        self.assertEqual(result["label"], "not applicable")

    def test_valid_change_filters_unknown_sentence_ids(self):
        result = ReviewerAgent._normalize(
            {"label": "not excluded", "reason": "not mentioned", "sentence_ids": [0, 9]}, self.request, {0: "x"}
        )
        self.assertEqual((result["label"], result["changed"], result["sentence_ids"]), ("not excluded", True, [0]))


if __name__ == "__main__":
    unittest.main()
