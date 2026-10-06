import unittest
from unittest import mock

from trialgpt_agents.targeted_review import negative_criteria, relevance_score, review_negative_labels

NOTE = "0. A 60-year-old man with melanoma.\n1. He had chemotherapy in 2019."
TRIAL = {
    "inclusion_criteria": "Adults with melanoma\n\nNo prior surgery",
    "exclusion_criteria": "Chemotherapy in the last 6 months",
}
MATCHING = {
    "inclusion": {"0": ["melanoma present", [0], "included"], "1": ["surgery unknown", [], "not included"]},
    "exclusion": {"0": ["chemo in 2019", [1], "excluded"]},
}


def reviewer_returning(results):
    reviewer = mock.Mock()
    reviewer.review_batch.side_effect = lambda chunk, sentences: {
        request["key"]: results.get(request["key"], {"label": request["original_label"], "changed": False})
        for request in chunk
    }
    return reviewer


class TargetedReviewTests(unittest.TestCase):
    def test_only_negative_labels_are_sent(self):
        keys = [item["key"] for item in negative_criteria(MATCHING, TRIAL)]
        self.assertEqual(keys, ["inclusion:1", "exclusion:0"])

    def test_relevant_trial_gets_its_negative_labels_reviewed(self):
        reviewer = reviewer_returning(
            {"exclusion:0": {"label": "not excluded", "changed": True, "reason": "2019 is not recent", "sentence_ids": [1]}}
        )
        reviewed, record = review_negative_labels(MATCHING, TRIAL, NOTE, 75.0, reviewer)
        self.assertTrue(record["selected"])
        self.assertEqual(reviewed["exclusion"]["0"], ["2019 is not recent", [1], "not excluded"])
        self.assertEqual(reviewed["inclusion"]["1"], MATCHING["inclusion"]["1"])  # reviewed, kept
        self.assertEqual(reviewed["inclusion"]["0"], MATCHING["inclusion"]["0"])  # never sent
        self.assertEqual([item["final_eligibility"] for item in record["criteria"]], ["not included", "not excluded"])
        self.assertEqual(MATCHING["exclusion"]["0"][2], "excluded")  # input left untouched

    def test_trial_below_the_cutoff_makes_no_call(self):
        reviewer = reviewer_returning({})
        reviewed, record = review_negative_labels(MATCHING, TRIAL, NOTE, 30.0, reviewer)
        reviewer.review_batch.assert_not_called()
        self.assertFalse(record["selected"])
        self.assertEqual(reviewed, MATCHING)

    def test_missing_relevance_means_not_reviewed(self):
        reviewer = reviewer_returning({})
        _, record = review_negative_labels(MATCHING, TRIAL, NOTE, None, reviewer)
        reviewer.review_batch.assert_not_called()
        self.assertFalse(record["selected"])

    def test_trial_without_negative_labels_makes_no_call(self):
        clean = {"inclusion": {"0": ["", [0], "included"]}, "exclusion": {"0": ["", [], "not excluded"]}}
        reviewer = reviewer_returning({})
        _, record = review_negative_labels(clean, TRIAL, NOTE, 90.0, reviewer)
        reviewer.review_batch.assert_not_called()
        self.assertFalse(record["selected"])

    def test_many_negative_labels_are_sent_in_chunks(self):
        criteria = "\n\n".join(f"Criterion number {index}" for index in range(23))
        matching = {"inclusion": {str(index): ["", [], "not included"] for index in range(23)}, "exclusion": {}}
        reviewer = reviewer_returning({})
        _, record = review_negative_labels(matching, {"inclusion_criteria": criteria}, NOTE, 90.0, reviewer)
        self.assertEqual(reviewer.review_batch.call_count, 3)
        self.assertEqual(len(record["criteria"]), 23)

    def test_relevance_score_parsing(self):
        self.assertEqual(relevance_score({"relevance_score_R": "65"}), 65.0)
        self.assertIsNone(relevance_score({"relevance_score_R": "high"}))
        self.assertIsNone(relevance_score("matching result error"))


if __name__ == "__main__":
    unittest.main()
