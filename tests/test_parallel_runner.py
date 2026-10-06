import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from evaluate_rankings import (
    cost_report,
    matching_score,
    ndcg_at_k,
    patient_cost,
    precision_at_k,
    rank_patient,
    review_applies,
    reviewed_trial_results,
    trial_score,
)
from run_parallel import JsonStore, Run, read_patients_file, select_patients
from trialgpt_assertion.TrialGPT import CachedNoteAssertion
from trialgpt_ranking.rank_results import get_agg_score, get_matching_score
from trialgpt_llm import client as llm_client
from trialgpt_llm.client import call_json, parse_retry_after, track_usage
from trialgpt_llm.key_pool import AllKeysExhausted, KeyPool, KeySlot


class FakeApiError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


class ScriptedClient:
    """Returns or raises the scripted outcomes in order."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(outcome)))],
            usage=SimpleNamespace(total_tokens=120),
        )


class RetryAfterParsingTests(unittest.TestCase):
    def test_parses_groq_duration_formats(self):
        self.assertAlmostEqual(parse_retry_after("Please try again in 7.5s."), 7.5)
        self.assertAlmostEqual(parse_retry_after("Please try again in 1m26.4s."), 86.4)
        self.assertAlmostEqual(parse_retry_after("Please try again in 2h3m."), 7380)
        self.assertAlmostEqual(parse_retry_after("Please try again in 450ms."), 0.45)
        self.assertIsNone(parse_retry_after("Something else went wrong."))

    def test_names_the_limit_that_was_hit(self):
        error = FakeApiError(429, "Rate limit reached for model `m` on tokens per day (TPD): Limit 500000")
        self.assertEqual(llm_client._limit_kind(error), "tokens per day (TPD)")
        itpm = FakeApiError(429, "service tier `on_demand` on input tokens per minute (ITPM): Limit 7000")
        self.assertEqual(llm_client._limit_kind(itpm), "input tokens per minute (ITPM)")
        self.assertEqual(llm_client._limit_kind(FakeApiError(429, "slow down")), "rate limit")


class KeyPoolTests(unittest.TestCase):
    def test_rotates_across_idle_keys(self):
        pool = KeyPool([KeySlot("a", None), KeySlot("b", None)])
        first = pool.acquire()
        pool.release(first)
        second = pool.acquire()
        self.assertNotEqual(first.name, second.name)

    def test_skips_cooling_key(self):
        pool = KeyPool([KeySlot("a", None), KeySlot("b", None)])
        slot_a = pool.acquire()
        pool.cooldown(slot_a, 60)
        pool.release(slot_a)
        for _ in range(3):
            slot = pool.acquire()
            self.assertEqual(slot.name, "b")
            pool.release(slot)

    def test_raises_when_every_key_cools_longer_than_max_wait(self):
        pool = KeyPool([KeySlot("a", None)], max_wait_seconds=5)
        slot = pool.acquire()
        pool.cooldown(slot, 3600)
        pool.release(slot)
        with self.assertRaises(AllKeysExhausted):
            pool.acquire()

    def test_waits_for_short_cooldown(self):
        pool = KeyPool([KeySlot("a", None)], max_wait_seconds=5)
        slot = pool.acquire()
        pool.cooldown(slot, 0.05)
        pool.release(slot)
        self.assertEqual(pool.acquire().name, "a")


class CallJsonPoolTests(unittest.TestCase):
    def test_rate_limited_key_hands_request_to_next_key(self):
        limited = ScriptedClient([FakeApiError(429, "Rate limit reached. Please try again in 30s.")])
        healthy = ScriptedClient([{"ok": True}])
        pool = KeyPool([KeySlot("a", limited), KeySlot("b", healthy)])
        with mock.patch.object(llm_client, "get_key_pool", return_value=pool):
            result = call_json("system", "user", "model")

        self.assertEqual(result, {"ok": True})
        self.assertEqual((limited.calls, healthy.calls), (1, 1))
        self.assertGreater(pool.slots[0].cooldown_until, pool.slots[1].cooldown_until)
        self.assertEqual([item["tokens"] for item in pool.summary()], [0, 120])

    def test_reasoning_effort_is_sent_only_when_configured(self):
        client = ScriptedClient([{"ok": True}, {"ok": True}])
        sent = []
        original = client.create
        client.chat.completions.create = lambda **kwargs: sent.append(kwargs) or original(**kwargs)
        with mock.patch.dict("os.environ", {"GROQ_REASONING_EFFORT": "low"}):
            call_json("system", "user", "model", client=client)
        with mock.patch.dict("os.environ", {"GROQ_REASONING_EFFORT": ""}):
            call_json("system", "user", "model", client=client)
        self.assertEqual(sent[0]["extra_body"], {"reasoning_effort": "low"})
        self.assertNotIn("extra_body", sent[1])

    def test_request_too_large_is_not_retried(self):
        client = ScriptedClient([FakeApiError(413, "Request too large for model.")])
        pool = KeyPool([KeySlot("a", client)])
        with mock.patch.object(llm_client, "get_key_pool", return_value=pool):
            with self.assertRaises(FakeApiError):
                call_json("system", "user", "model")
        self.assertEqual(client.calls, 1)

    def test_status_code_wins_over_message_text(self):
        # A 400 whose message happens to mention "429" is a real error, not a rate limit.
        client = ScriptedClient([FakeApiError(400, "bad request id req_429abc")])
        pool = KeyPool([KeySlot("a", client)])
        with mock.patch.object(llm_client, "get_key_pool", return_value=pool):
            with self.assertRaises(FakeApiError):
                call_json("system", "user", "model")


class UsageTrackingTests(unittest.TestCase):
    def test_counts_tokens_of_calls_made_inside_the_block(self):
        client = ScriptedClient([{"ok": True}, {"ok": True}, {"ok": True}])
        with track_usage() as usage:
            call_json("system", "user", "model", client=client)
            call_json("system", "user", "model", client=client)
        call_json("system", "user", "model", client=client)  # outside: not counted
        self.assertEqual((usage["calls"], usage["total_tokens"]), (2, 240))

    def test_threads_keep_separate_totals(self):
        results = {}

        def work(name, calls):
            client = ScriptedClient([{"ok": True}] * calls)
            with track_usage() as usage:
                for _ in range(calls):
                    call_json("system", "user", "model", client=client)
            results[name] = usage["calls"]

        threads = [threading.Thread(target=work, args=(name, calls)) for name, calls in (("a", 1), ("b", 3))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results, {"a": 1, "b": 3})


class StageTests(unittest.TestCase):
    instance = {"patient_id": "test-patient-not-in-results", "2": [{"NCTID": "NCT-A"}], "0": [{"NCTID": "NCT-B"}]}
    trial = {"NCTID": "NCT-A", "inclusion_criteria": "Adults with melanoma", "exclusion_criteria": "Prior chemotherapy"}

    def test_trialgpt_only_run_counts_matching_and_aggregation(self):
        run = Run("sigir", "test-model", {"match", "aggregate"})
        # per trial: 2 matching calls + 1 aggregation
        self.assertEqual(run.remaining_calls(self.instance), 6)

    def test_full_run_adds_one_estimated_review_call_per_unmatched_trial(self):
        run = Run("sigir", "test-model", {"match", "aggregate", "review"})
        self.assertEqual(run.remaining_calls(self.instance), 8)

    def review_run(self, tmp, relevance, label="not included", min_relevance=50.0):
        run = Run("sigir", "test-model", {"review"}, min_relevance)
        for name in ("matching", "aggregation", "reviewed", "review_log", "usage"):
            setattr(run, name, JsonStore(Path(tmp) / f"{name}.json", indent=0))
        run.matching.put("p", "2", "NCT-A", {
            "inclusion": {"0": ["no melanoma found", [0], label]},
            "exclusion": {"0": ["no chemotherapy", [], "not excluded"]},
        })
        run.aggregation.put("p", "NCT-A", {"relevance_score_R": relevance, "eligibility_score_E": 0})
        run.reviewer = mock.Mock()
        run.reviewer.review_batch.return_value = {
            "inclusion:0": {"label": "included", "changed": True, "reason": "melanoma in sentence 0", "sentence_ids": [0]}
        }
        return run

    def test_review_fixes_negative_label_on_relevant_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.review_run(tmp, relevance=80)
            self.assertEqual(run.remaining_work({"patient_id": "p", "2": [self.trial]}), (1, 1))
            ran = run.process_trial("p", "2", self.trial, "0. Melanoma of the arm.")
            self.assertEqual(run.reviewed.get("p", "2", "NCT-A")["inclusion"]["0"][2], "included")
            self.assertTrue(run.review_log.get("p", "NCT-A")["selected"])
            self.assertIn("1 changed", ran)
            self.assertTrue(run.review_done("p", "NCT-A"))
            self.assertEqual(run.remaining_work({"patient_id": "p", "2": [self.trial]}), (0, 0))

    def test_irrelevant_trial_is_recorded_without_a_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.review_run(tmp, relevance=20)
            self.assertEqual(run.remaining_work({"patient_id": "p", "2": [self.trial]}), (0, 1))
            run.process_trial("p", "2", self.trial, "0. Melanoma of the arm.")
            run.reviewer.review_batch.assert_not_called()
            self.assertFalse(run.review_log.get("p", "NCT-A")["selected"])
            self.assertEqual(run.usage.get("p", "NCT-A", "review")["calls"], 0)
            self.assertEqual(run.reviewed.get("p", "2", "NCT-A"), run.matching.get("p", "2", "NCT-A"))

    def test_lower_cutoff_redoes_reviews_made_with_a_higher_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.review_run(tmp, relevance=20)
            run.process_trial("p", "2", self.trial, "0. Melanoma of the arm.")
            run.min_relevance = 10.0
            self.assertFalse(run.review_done("p", "NCT-A"))


class ScoreTests(unittest.TestCase):
    result = {
        "inclusion": {"0": ["", [], "included"], "1": ["", [], "not included"], "2": ["", [], "not enough information"]},
        "exclusion": {"0": ["", [], "excluded"], "1": ["", [], "not excluded"]},
    }
    assessment = {"relevance_score_R": 70, "eligibility_score_E": 20}

    def test_defaults_match_trialgpt_formula(self):
        official = get_matching_score(self.result) + get_agg_score(self.assessment)
        self.assertAlmostEqual(trial_score(self.result, self.assessment), official)

    def test_penalty_and_weight(self):
        self.assertAlmostEqual(matching_score(self.result, penalty=0.25), 1 / 3 - 0.5, places=6)
        self.assertAlmostEqual(trial_score(self.result, self.assessment, 0.0, 2.0), 1 / 3 + 1.8, places=6)

    def test_smaller_penalty_lifts_a_relevant_trial_with_one_negative_label(self):
        good = {"inclusion": {"0": ["", [], "included"], "1": ["", [], "not included"]}, "exclusion": {}}
        unrelated = {"inclusion": {"0": ["", [], "included"], "1": ["", [], "not enough information"]}, "exclusion": {}}
        matching = {"p": {"2": {"GOOD": good}, "0": {"OTHER": unrelated}}}
        aggregation = {"p": {"GOOD": {"relevance_score_R": 80, "eligibility_score_E": 20},
                             "OTHER": {"relevance_score_R": 30, "eligibility_score_E": 0}}}
        self.assertEqual(rank_patient("p", ["GOOD", "OTHER"], matching, aggregation), ["OTHER", "GOOD"])
        self.assertEqual(rank_patient("p", ["GOOD", "OTHER"], matching, aggregation, penalty=0.25), ["GOOD", "OTHER"])


class ReviewedResultTests(unittest.TestCase):
    before = {"p": {"2": {"A": {"inclusion": {"0": ["", [], "not included"]}, "exclusion": {}}},
                    "0": {"B": {"inclusion": {}, "exclusion": {}}}}}
    after = {"p": {"2": {"A": {"inclusion": {"0": ["", [], "included"]}, "exclusion": {}}},
                   "0": {"B": {"inclusion": {}, "exclusion": {}}}}}
    log = {"p": {"A": {"selected": True, "relevance": 60, "min_relevance": 50},
                 "B": {"selected": False, "relevance": 10, "min_relevance": 50}}}

    def test_review_counts_only_above_the_cutoff(self):
        results, applied = reviewed_trial_results("p", ["A", "B"], self.before, self.after, self.log, None)
        self.assertEqual(results["A"]["inclusion"]["0"][2], "included")
        self.assertEqual(applied, {"A"})
        results, applied = reviewed_trial_results("p", ["A", "B"], self.before, self.after, self.log, 70)
        self.assertEqual(results["A"]["inclusion"]["0"][2], "not included")
        self.assertEqual(applied, set())

    def test_cutoff_below_the_run_cutoff_is_refused(self):
        with self.assertRaises(SystemExit):
            review_applies({"selected": False, "relevance": 10, "min_relevance": 50}, 30)

    def test_missing_review_record_means_incomplete(self):
        self.assertIsNone(reviewed_trial_results("p", ["A", "C"], self.before, self.after, self.log, None))


class CostReportTests(unittest.TestCase):
    @staticmethod
    def stage(tokens):
        return {"calls": 1, "prompt_tokens": tokens, "completion_tokens": 0, "total_tokens": tokens, "seconds": 1.0}

    def usage(self):
        return {"p": {"NCT1": {"match": self.stage(100), "agg-baseline": self.stage(20), "review": self.stage(30)},
                      "NCT2": {"match": self.stage(100), "agg-baseline": self.stage(20), "review": self.stage(0)}}}

    def test_baseline_and_reviewed_costs_and_overhead(self):
        report = cost_report(["p"], {"p": ["NCT1", "NCT2"]}, self.usage())
        self.assertEqual(report["baseline"]["total_tokens"], 240)
        self.assertEqual(report["reviewed"]["total_tokens"], 270)
        self.assertAlmostEqual(report["overhead_tokens_pct"], 12.5)

    def test_simulated_cutoff_counts_only_reviews_that_count(self):
        report = cost_report(["p"], {"p": ["NCT1", "NCT2"]}, self.usage(), reviewed_trials={"p": set()})
        self.assertEqual(report["reviewed"]["total_tokens"], 240)

    def test_baseline_only_cost(self):
        usage = {"p": {"NCT1": {"match": self.stage(100), "agg-baseline": self.stage(20)}}}
        report = cost_report(["p"], {"p": ["NCT1"]}, usage, ("baseline",))
        self.assertEqual(report["baseline"]["total_tokens"], 120)
        self.assertNotIn("reviewed", report)

    def test_patient_with_unrecorded_stage_is_left_out(self):
        usage = {"NCT1": {"match": self.stage(100), "agg-baseline": self.stage(20)}}
        self.assertIsNone(patient_cost(usage, ["NCT1"]))


class JsonStoreTests(unittest.TestCase):
    def test_put_persists_nested_values_and_reloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.json"
            store = JsonStore(path, indent=2)
            store.put("patient", "2", "NCT1", {"inclusion": {}})
            self.assertEqual(store.get("patient", "2", "NCT1"), {"inclusion": {}})
            self.assertIsNone(store.get("patient", "1", "NCT1"))
            self.assertEqual(JsonStore(path, indent=2).get("patient", "2", "NCT1"), {"inclusion": {}})
            self.assertFalse((Path(tmp) / "results.json.tmp").exists())

    def test_concurrent_puts_keep_every_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.json"
            store = JsonStore(path, indent=None)
            threads = [
                threading.Thread(target=store.put, args=("patient", f"NCT{index}", index))
                for index in range(40)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(json.loads(path.read_text())["patient"]), 40)


class PatientSelectionTests(unittest.TestCase):
    def test_patients_file_order_is_kept_and_comments_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "patients.txt"
            path.write_text("# header\nsigir-3\n\nsigir-1  # smallest\n")
            ids = read_patients_file(path)
        dataset = [{"patient_id": f"sigir-{index}"} for index in (1, 2, 3)]
        self.assertEqual(ids, ["sigir-3", "sigir-1"])
        self.assertEqual([item["patient_id"] for item in select_patients(dataset, ids, 0)], ["sigir-3", "sigir-1"])

    def test_unknown_patient_id_is_rejected(self):
        with self.assertRaises(SystemExit):
            select_patients([{"patient_id": "sigir-1"}], ["sigir-9"], 0)


class CachedNoteAssertionTests(unittest.TestCase):
    def test_classifies_note_once_per_patient(self):
        agent = mock.Mock()
        agent.analyze_patient_note.return_value = {"usable_sentence_ids": [0]}
        cached = CachedNoteAssertion(agent)
        for _ in range(3):
            self.assertEqual(cached.analyze_patient_note({0: "x"}), {"usable_sentence_ids": [0]})
        agent.analyze_patient_note.assert_called_once()


class RankingMetricTests(unittest.TestCase):
    def test_ties_are_broken_by_trial_id_not_file_order(self):
        result = {"inclusion": {}, "exclusion": {}}
        assessment = {"relevance_score_R": 50, "eligibility_score_E": 0}
        matching = {"p": {"2": {"NCT9": result}, "0": {"NCT1": result}}}
        aggregation = {"p": {"NCT9": assessment, "NCT1": assessment}}
        self.assertEqual(rank_patient("p", ["NCT9", "NCT1"], matching, aggregation), ["NCT1", "NCT9"])

    def test_incomplete_patient_is_not_ranked(self):
        result = {"inclusion": {}, "exclusion": {}}
        matching = {"p": {"2": {"NCT1": result, "NCT2": result}}}
        aggregation = {"p": {"NCT1": {"relevance_score_R": 1, "eligibility_score_E": 1}}}
        self.assertIsNone(rank_patient("p", ["NCT1", "NCT2"], matching, aggregation))

    def test_ndcg_and_precision(self):
        judgments = {"A": 2, "B": 0, "C": 1}
        self.assertAlmostEqual(ndcg_at_k(["A", "C", "B"], judgments), 1.0)
        self.assertLess(ndcg_at_k(["B", "C", "A"], judgments), 1.0)
        self.assertAlmostEqual(precision_at_k(["A", "C", "B"], judgments), 0.1)


if __name__ == "__main__":
    unittest.main()
