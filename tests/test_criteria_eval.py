import unittest

from evaluate_criteria import _mcnemar_p, build_pair_input, reviewable, score


def row(annotation_id, gpt4, expert, criterion="Patient has asthma", criterion_type="inclusion", trial="NCT1"):
    return {
        "annotation_id": annotation_id,
        "patient_id": "sigir-1",
        "trial_id": trial,
        "note": "0. The patient has asthma.\n1. The patient will provide informed consent.",
        "criterion_type": criterion_type,
        "criterion_text": criterion,
        "gpt4_explanation": "reason",
        "gpt4_sentences": "[0]",
        "expert_sentences": "[0]",
        "gpt4_eligibility": gpt4,
        "expert_eligibility": expert,
    }


class ScoreTests(unittest.TestCase):
    def test_counts_fixed_broken_and_accuracy(self):
        rows = [
            row(1, "not applicable", "not excluded", criterion_type="exclusion"),  # GPT-4 wrong, agent fixes; int ID like the dataset
            row("2", "included", "included"),  # GPT-4 right, agent breaks
            row("3", "included", "included", criterion="Age over 18 years"),  # untouched
        ]
        store = {"sigir-1|NCT1": {"labels": {
            "1": {"final_eligibility": "not excluded", "final_sentences": [0]},
            "2": {"final_eligibility": "not enough information", "final_sentences": []},
            "3": {"final_eligibility": "included", "final_sentences": [0]},
        }, "usage": {"calls": 2, "total_tokens": 900}}}
        report = score(rows, store)
        self.assertAlmostEqual(report["baseline_accuracy"], 2 / 3)
        self.assertAlmostEqual(report["agent_accuracy"], 2 / 3)
        self.assertEqual((report["fixed"], report["broken"], report["changed"]), (1, 1, 2))
        self.assertEqual(report["tokens_per_criterion"], 300)
        self.assertAlmostEqual(report["evidence"]["agents"]["recall"], 2 / 3)

    def test_unreviewed_pairs_are_not_scored(self):
        report = score([row("1", "included", "included")], {})
        self.assertEqual(report["scored"], 0)

    def test_mcnemar(self):
        self.assertIsNone(_mcnemar_p(0, 0))
        self.assertAlmostEqual(_mcnemar_p(5, 5), 1.0)
        self.assertLess(_mcnemar_p(12, 1), 0.01)


class PairInputTests(unittest.TestCase):
    def test_numbering_matches_trialgpt_and_skips_unparseable_criteria(self):
        rows = [
            row("1", "included", "included", criterion="Patient has asthma"),
            row("2", "included", "included", criterion="none"),
            row("3", "not excluded", "not excluded", criterion="Active smoker", criterion_type="exclusion"),
        ]
        self.assertFalse(reviewable(rows[1]))
        matching, trial, note, id_map = build_pair_input(rows)
        self.assertEqual(id_map, {("inclusion", "0"): "1", ("exclusion", "0"): "3"})
        self.assertEqual(matching["inclusion"]["0"], ["reason", [0], "included"])
        self.assertEqual(trial["exclusion_criteria"], "Active smoker")


if __name__ == "__main__":
    unittest.main()
