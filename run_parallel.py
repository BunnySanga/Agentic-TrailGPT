#!/usr/bin/env python3
"""Run matching, the three agents, and aggregation for several patients at once.

Usage:
    python run_parallel.py --limit 10            # first 10 patients (finished ones are skipped)
    python run_parallel.py --patient-ids sigir-20145,sigir-20146
    python run_parallel.py --limit 10 --dry-run  # only estimate the API calls left
    python run_parallel.py --patients-file study_patients.txt --max-minutes 8
    python run_parallel.py --patients-file ranking_dev_patients.txt --stages match,aggregate   # baseline only

Options: --corpus sigir  --model MODEL  --workers 3  --stages match,enhance,aggregate

Exit codes: 0 = pass finished, 2 = --max-minutes reached with work left,
3 = every key hit its rate limit for longer than KEY_MAX_WAIT_SECONDS (daily cap).
The last line printed is machine-readable: RESULT status=... remaining_calls=N ...

Each worker takes one patient and carries every trial through
    match -> enhance (Assertion, Clarification, Verifier) -> aggregate baseline -> aggregate enhanced
so patients finish completely one after another. All Groq calls share the key
pool from GROQ_API_KEYS. Results go to the same files the official scripts use
and are saved after every step, so an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from dotenv import load_dotenv
from nltk.tokenize import sent_tokenize

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from evaluate_rankings import evaluate, print_report
from trialgpt_agents.enhanced_matching import enhance_trial_matching
from trialgpt_assertion.TrialGPT import AssertionAgent
from trialgpt_clarification.TrialGPT import ClarificationAgent
from trialgpt_llm.client import track_usage
from trialgpt_llm.key_pool import AllKeysExhausted, get_key_pool
from trialgpt_matching.TrialGPT import trialgpt_matching
from trialgpt_ranking.TrialGPT import trialgpt_aggregation
from trialgpt_verifier.TrialGPT import VerifierAgent

STAGES = ("match", "enhance", "aggregate")
EXIT_DONE = 0
EXIT_TIME_UP = 2
EXIT_DAILY_LIMIT = 3
CONSENT_SENTENCE = (
    "The patient will provide informed consent, and will comply with the trial protocol without any practical issues."
)


class JsonStore:
    """A nested JSON results file shared by worker threads.

    Every ``put`` rewrites the file atomically (temp file + rename), so the
    file on disk is always complete even if the run is killed mid-write.
    """

    def __init__(self, path: Path, indent: int):
        self.path = path
        self.indent = indent
        self._lock = threading.Lock()
        self._data = json.loads(path.read_text()) if path.exists() else {}

    def get(self, *keys: str):
        with self._lock:
            node = self._data
            for key in keys:
                if not isinstance(node, dict) or key not in node:
                    return None
                node = node[key]
            return node

    def put(self, *keys_and_value) -> None:
        *keys, value = keys_and_value
        with self._lock:
            node = self._data
            for key in keys[:-1]:
                node = node.setdefault(key, {})
            node[keys[-1]] = value
            tmp = self.path.with_name(self.path.name + ".tmp")
            with tmp.open("w") as handle:
                json.dump(self._data, handle, indent=self.indent)
            os.replace(tmp, self.path)


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


def number_patient_note(text: str) -> str:
    """Number note sentences exactly as the official run_matching.py does."""
    sentences = sent_tokenize(text)
    sentences.append(CONSENT_SENTENCE)
    return "\n".join(f"{index}. {sentence}" for index, sentence in enumerate(sentences))


class Run:
    def __init__(self, corpus: str, model: str, stages: set[str]):
        model_safe = model.replace("/", "_")
        results = PROJECT_ROOT / "results"
        results.mkdir(exist_ok=True)
        self.model = model
        self.stages = stages
        self.matching = JsonStore(results / f"matching_results_{corpus}_{model_safe}.json", indent=4)
        self.enhanced = JsonStore(results / f"matching_results_{corpus}_{model_safe}_enhanced.json", indent=2)
        self.review = JsonStore(results / f"matching_results_{corpus}_{model_safe}_enhanced_review.json", indent=2)
        self.agg_baseline = JsonStore(results / f"aggregation_results_{corpus}_{model_safe}_baseline.json", indent=4)
        self.agg_enhanced = JsonStore(results / f"aggregation_results_{corpus}_{model_safe}_enhanced.json", indent=4)
        # Token usage per patient / trial / stage, for the baseline vs agents cost comparison.
        self.usage = JsonStore(results / f"usage_{corpus}_{model_safe}.json", indent=2)
        # Without the enhance stage this is a baseline-only run: no enhanced
        # aggregation is expected.
        self.with_agents = "enhance" in stages
        self.stop = threading.Event()
        self.stop_reason = ""
        self._stats_lock = threading.Lock()
        self.errors = 0
        self.completed_patients: list[str] = []

    # ---- what is already done -------------------------------------------------

    def enhanced_done(self, patient_id: str, label: str, trial_id: str) -> bool:
        review = self.review.get(patient_id, trial_id)
        return (
            self.enhanced.get(patient_id, label, trial_id) is not None
            and isinstance(review, dict)
            and review.get("agent_mode") == "llm_batched"
            and "error" not in review
        )

    def remaining_calls(self, instance: dict) -> int:
        """Estimate Groq calls still needed for one patient."""
        patient_id = instance["patient_id"]
        calls = 0
        needs_assertion = False
        for label in ("2", "1", "0"):
            for trial in instance.get(label, []):
                trial_id = trial["NCTID"]
                if "match" in self.stages and not isinstance(self.matching.get(patient_id, label, trial_id), dict):
                    calls += 2
                if "enhance" in self.stages and not self.enhanced_done(patient_id, label, trial_id):
                    calls += 2
                    needs_assertion = True
                if "aggregate" in self.stages:
                    calls += self.agg_baseline.get(patient_id, trial_id) is None
                    if self.with_agents:
                        calls += self.agg_enhanced.get(patient_id, trial_id) is None
        return calls + needs_assertion

    def patient_complete(self, instance: dict) -> bool:
        patient_id = instance["patient_id"]
        return all(
            isinstance(self.agg_baseline.get(patient_id, trial["NCTID"]), dict)
            and (not self.with_agents or isinstance(self.agg_enhanced.get(patient_id, trial["NCTID"]), dict))
            for label in ("2", "1", "0")
            for trial in instance.get(label, [])
        )

    # ---- work -------------------------------------------------------------------

    def process_patient(self, instance: dict, note: str) -> None:
        patient_id = instance["patient_id"]
        trials = [(label, trial) for label in ("2", "1", "0") for trial in instance.get(label, [])]
        agents = (
            CachedNoteAssertion(AssertionAgent(self.model)),
            ClarificationAgent(self.model),
            VerifierAgent(self.model),
        )
        started = time.time()
        print(f"[{patient_id}] start: {len(trials)} trials", flush=True)

        for index, (label, trial) in enumerate(trials, 1):
            if self.stop.is_set():
                return
            trial_id = trial["NCTID"]
            try:
                done = self.process_trial(patient_id, label, trial, note, agents)
            except AllKeysExhausted as error:
                self.stop_reason = str(error)
                self.stop.set()
                return
            except Exception as error:
                with self._stats_lock:
                    self.errors += 1
                print(f"[{patient_id}] {trial_id} error: {str(error)[:200]}", flush=True)
                continue
            if done:
                print(f"[{patient_id}] {index}/{len(trials)} {trial_id} {done}", flush=True)

        if self.patient_complete(instance):
            with self._stats_lock:
                self.completed_patients.append(patient_id)
            print(f"[{patient_id}] complete in {(time.time() - started) / 60:.1f} min", flush=True)

    def process_trial(self, patient_id: str, label: str, trial: dict, note: str, agents) -> str:
        """Run every missing stage for one trial; return a short log of what ran."""
        trial_id = trial["NCTID"]
        ran = []

        matching = self.matching.get(patient_id, label, trial_id)
        if "match" in self.stages and not isinstance(matching, dict):
            with track_usage() as usage:
                matching = trialgpt_matching(trial, note, self.model)
            self.matching.put(patient_id, label, trial_id, matching)
            self.usage.put(patient_id, trial_id, "match", usage)
            ran.append("match")
        if not isinstance(matching, dict):
            return " ".join(ran)

        if "enhance" in self.stages and not self.enhanced_done(patient_id, label, trial_id):
            assertion, clarification, verifier = agents
            # The note-level assertion runs once per patient, so its tokens
            # land on that patient's first enhanced trial.
            with track_usage() as usage:
                enhanced, review = enhance_trial_matching(
                    matching,
                    trial,
                    note,
                    model=self.model,
                    assertion_agent=assertion,
                    clarification_agent=clarification,
                    verifier_agent=verifier,
                )
            self.enhanced.put(patient_id, label, trial_id, enhanced)
            self.review.put(patient_id, trial_id, review)
            self.usage.put(patient_id, trial_id, "enhance", usage)
            ran.append("enhance")

        if "aggregate" in self.stages:
            for name, source, target in (
                ("agg-baseline", self.matching, self.agg_baseline),
                ("agg-enhanced", self.enhanced, self.agg_enhanced),
            ):
                if target.get(patient_id, trial_id) is not None:
                    continue
                result = source.get(patient_id, label, trial_id)
                if result is None:
                    continue
                if not isinstance(result, dict):
                    target.put(patient_id, trial_id, "matching result error")
                    continue
                # The retrieved trial is the text matching numbered its criteria
                # from, so aggregation maps criterion IDs back to the same text.
                with track_usage() as usage:
                    aggregation = trialgpt_aggregation(note, result, trial, self.model)
                target.put(patient_id, trial_id, aggregation)
                self.usage.put(patient_id, trial_id, name, usage)
                ran.append(name)

        return " ".join(ran)


def select_patients(dataset: list[dict], patient_ids: list[str], limit: int) -> list[dict]:
    """Pick patients by ID in the given order, or the first ``limit`` in dataset order."""
    selected = dataset
    if patient_ids:
        by_id = {item["patient_id"]: item for item in dataset}
        missing = [patient_id for patient_id in patient_ids if patient_id not in by_id]
        if missing:
            raise SystemExit(f"Unknown patient IDs: {', '.join(missing)}")
        selected = [by_id[patient_id] for patient_id in dict.fromkeys(patient_ids)]
    return selected[:limit] if limit > 0 else selected


def read_patients_file(path: Path) -> list[str]:
    """One patient ID per line; blank lines and # comments are ignored."""
    ids = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    return ids


def print_summary(
    run: Run, pool, started: float, status: str, remaining: int, corpus: str, model: str,
    patient_ids: list[str], show_scores: bool = True,
) -> None:
    print("\n" + "=" * 70)
    if run.stop_reason:
        print(f"Stopped: {run.stop_reason}")
    print(f"Ran {(time.time() - started) / 60:.1f} min | patients completed: "
          f"{len(run.completed_patients)} | trial errors: {run.errors}")
    summary = pool.summary()
    print("Usage per key:")
    for item in summary:
        print(f"  {item['key']}  requests {item['requests']:>4}  tokens {item['tokens']:>8,}  rate-limited {item['rate_limited']:>3}")
    total_tokens = sum(item["tokens"] for item in summary)
    print(f"  total tokens this run: {total_tokens:,}")
    if run.errors:
        print("Trials with errors were not saved; the next run retries them.")
    if show_scores:
        variants = ("baseline", "enhanced") if run.with_agents else ("baseline",)
        print_report(evaluate(corpus, model, variants=variants, patient_ids=patient_ids))
    print(
        f"RESULT status={status} remaining_calls={remaining} "
        f"completed_patients={','.join(run.completed_patients) or '-'} "
        f"trial_errors={run.errors} tokens={total_tokens}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", default="sigir")
    parser.add_argument("--model", default=os.getenv("MODEL", "qwen/qwen3.8-27b"))
    parser.add_argument("--limit", type=int, default=None,
                        help="first N patients in dataset order; 0 = all (default: PATIENT_LIMIT, "
                             "ignored when patients are listed)")
    parser.add_argument("--patient-ids", default="", help="comma-separated patient IDs")
    parser.add_argument("--patients-file", type=Path, help="file with one patient ID per line, processed in order")
    parser.add_argument("--workers", type=int, default=int(os.getenv("MAX_WORKERS", "3")))
    parser.add_argument("--stages", default=",".join(STAGES))
    parser.add_argument("--max-minutes", type=float, default=0,
                        help="stop after this many minutes (saved work is kept); 0 = no limit")
    parser.add_argument("--dry-run", action="store_true", help="estimate remaining API calls and exit")
    parser.add_argument("--no-report", action="store_true",
                        help="skip the ranking scores in the summary (for held-out patients)")
    args = parser.parse_args()

    stages = {stage.strip() for stage in args.stages.split(",") if stage.strip()}
    unknown = stages - set(STAGES)
    if unknown:
        raise SystemExit(f"Unknown stages: {', '.join(sorted(unknown))}. Choose from {', '.join(STAGES)}.")

    patient_ids = [patient_id.strip() for patient_id in args.patient_ids.split(",") if patient_id.strip()]
    if args.patients_file:
        patient_ids += read_patients_file(args.patients_file)
    limit = args.limit
    if limit is None:
        limit = 0 if patient_ids else int(os.getenv("PATIENT_LIMIT", "0"))

    with (PROJECT_ROOT / "dataset" / args.corpus / "retrieved_trials.json").open() as handle:
        dataset = json.load(handle)
    patients = select_patients(dataset, patient_ids, limit)

    run = Run(args.corpus, args.model, stages)
    # Tokenize in the main thread first: NLTK loads punkt lazily and the first
    # load is not safe to race from several threads.
    notes = {item["patient_id"]: number_patient_note(item["patient"]) for item in patients}
    todo = [(item, run.remaining_calls(item)) for item in patients]
    todo = [(item, calls) for item, calls in todo if calls > 0]
    total_calls = sum(calls for _, calls in todo)

    pool = get_key_pool()
    print("=" * 70)
    print(f"Model {args.model} | corpus {args.corpus} | stages {','.join(s for s in STAGES if s in stages)}")
    print(f"Patients selected {len(patients)} | with work left {len(todo)} | workers {args.workers} | keys {len(pool.slots)}")
    print(f"Estimated Groq calls: {total_calls} (pool allows about {1000 * len(pool.slots)}/day)")
    print("=" * 70, flush=True)
    if args.dry_run or not todo:
        status = "dry_run" if args.dry_run else "done"
        print(f"RESULT status={status} remaining_calls={total_calls} completed_patients=- trial_errors=0 tokens=0", flush=True)
        return EXIT_DONE

    started = time.time()
    deadline = started + args.max_minutes * 60 if args.max_minutes > 0 else None
    executor = ThreadPoolExecutor(max_workers=args.workers)
    pending = {executor.submit(run.process_patient, item, notes[item["patient_id"]]) for item, _ in todo}
    try:
        while pending:
            done, pending = wait(pending, timeout=5, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
            if run.stop.is_set() or (deadline and time.time() >= deadline):
                break
    except KeyboardInterrupt:
        # Every saved step is already on disk; exit without waiting for
        # in-flight requests. Re-running resumes from the saved results.
        print("\nInterrupted. Saved results are kept; re-run the same command to resume.", flush=True)
        os._exit(130)

    remaining = sum(run.remaining_calls(item) for item in patients)
    if run.stop.is_set():
        status, code = "daily_limit", EXIT_DAILY_LIMIT
    elif pending:
        run.stop.set()
        run.stop_reason = f"--max-minutes {args.max_minutes:g} reached; re-run to continue."
        status, code = "time_up", EXIT_TIME_UP
    else:
        status, code = "done", EXIT_DONE
    print_summary(run, pool, started, status, remaining, args.corpus, args.model,
                  [item["patient_id"] for item in patients], show_scores=not args.no_report)

    if pending:
        # Workers may be mid-request or waiting out a cooldown. Everything
        # finished is saved, so exit now instead of waiting for them.
        sys.stdout.flush()
        os._exit(code)
    executor.shutdown(wait=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
