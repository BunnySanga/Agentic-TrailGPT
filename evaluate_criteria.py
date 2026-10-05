#!/usr/bin/env python3
"""Score post-matching agents against TrialGPT's physician criterion annotations.

dataset/criterion_annotations.json (from huggingface.co/datasets/ncbi/TrialGPT-Criterion-Annotations)
holds 1,015 SIGIR patient-criterion pairs with GPT-4 TrialGPT predictions and
physician labels. GPT-4's labels are the baseline (87.3% accuracy). An agent
variant reviews GPT-4's output for each patient-trial pair, and its final
labels are scored against the physicians.

Usage:
    python evaluate_criteria.py --variant v1 --split dev --sample 300 --max-minutes 8
    python evaluate_criteria.py --variant v1 --split test
    python evaluate_criteria.py --variant v1 --split dev --sample 300 --report-only

Variants: v1 = Assertion + Clarification + Verifier on every criterion;
v2 = Assertion + one Reviewer on risky labels only; v3 = v2 without
reviewing "not enough information" labels.

Splits are by patient: test = the patients in criteria_test_patients.txt,
dev = everyone else. Develop agent prompts on dev only; score test once.
--sample N takes a fixed, seeded subset of whole patient-trial pairs with at
least N criteria, so every variant is scored on the same rows.

Exit codes match run_parallel.py: 0 = finished, 2 = --max-minutes reached,
3 = daily API limit. The last line printed is machine-readable (RESULT ...).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_parallel import (
    EXIT_DAILY_LIMIT,
    EXIT_DONE,
    EXIT_TIME_UP,
    CachedNoteAssertion,
    JsonStore,
    read_patients_file,
)
from trialgpt_agents.enhanced_matching import criteria_by_id, enhance_trial_matching
from trialgpt_agents.reviewed_matching import V3_KEEP_LABELS, V3_REVIEW_LABELS, review_trial_matching
from trialgpt_assertion.TrialGPT import AssertionAgent
from trialgpt_clarification.TrialGPT import ClarificationAgent
from trialgpt_llm.client import track_usage
from trialgpt_llm.key_pool import AllKeysExhausted, get_key_pool
from trialgpt_reviewer.TrialGPT import ReviewerAgent
from trialgpt_verifier.TrialGPT import VerifierAgent

DATASET = PROJECT_ROOT / "dataset" / "criterion_annotations.json"
TEST_PATIENTS = PROJECT_ROOT / "criteria_test_patients.txt"
SAMPLE_SEED = 2024


VARIANTS = ("v1", "v2", "v3")


def build_enhancer(variant: str, model: str):
    """Return a per-patient function (matching, trial, note) -> (enhanced, review)."""
    if variant == "v1":
        assertion = CachedNoteAssertion(AssertionAgent(model))
        clarification, verifier = ClarificationAgent(model), VerifierAgent(model)
        return lambda matching, trial, note: enhance_trial_matching(
            matching, trial, note, model=model,
            assertion_agent=assertion, clarification_agent=clarification, verifier_agent=verifier,
        )
    if variant == "v2":
        assertion, reviewer = CachedNoteAssertion(AssertionAgent(model)), ReviewerAgent(model)
        return lambda matching, trial, note: review_trial_matching(
            matching, trial, note, model=model, assertion_agent=assertion, reviewer_agent=reviewer,
        )
    if variant == "v3":
        assertion, reviewer = CachedNoteAssertion(AssertionAgent(model)), ReviewerAgent(model)
        return lambda matching, trial, note: review_trial_matching(
            matching, trial, note, model=model, assertion_agent=assertion, reviewer_agent=reviewer,
            review_labels=V3_REVIEW_LABELS, keep_labels=V3_KEEP_LABELS, agent_mode="llm_reviewer_v3",
        )
    raise SystemExit(f"Unknown variant {variant!r}. Available: {', '.join(VARIANTS)}")


def decision(record: dict) -> str | None:
    """Short description of what the agents decided for one criterion."""
    if record.get("verifier"):
        return record["verifier"].get("verdict")
    if not record.get("reviewed"):
        return "not reviewed"
    return "changed" if (record.get("reviewer") or {}).get("changed") else "kept"


# ---- data ----------------------------------------------------------------------

def load_rows() -> list[dict]:
    with DATASET.open() as handle:
        return json.load(handle)


def pair_key(row: dict) -> str:
    return f"{row['patient_id']}|{row['trial_id']}"


def reviewable(row: dict) -> bool:
    """True if TrialGPT's criterion parser keeps this criterion text."""
    text = row.get("criterion_text")
    return isinstance(text, str) and criteria_by_id(text.strip()) == {"0": text.strip()}


def select_rows(rows: list[dict], split: str, sample: int) -> list[dict]:
    test_patients = set(read_patients_file(TEST_PATIENTS))
    if split == "dev":
        rows = [row for row in rows if row["patient_id"] not in test_patients]
    elif split == "test":
        rows = [row for row in rows if row["patient_id"] in test_patients]
    if sample <= 0:
        return rows
    by_pair: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_pair[pair_key(row)].append(row)
    pairs = sorted(by_pair)
    random.Random(SAMPLE_SEED).shuffle(pairs)
    chosen: list[dict] = []
    for key in pairs:
        if len(chosen) >= sample:
            break
        chosen.extend(by_pair[key])
    return chosen


def build_pair_input(pair_rows: list[dict]) -> tuple[dict, dict, str, dict]:
    """Turn annotated rows into TrialGPT's matching format for the agents.

    Returns (matching_result, trial, numbered_note, criterion -> annotation_id).
    Only criteria TrialGPT's parser keeps are included; the rest keep GPT-4's label.
    """
    matching = {"inclusion": {}, "exclusion": {}}
    trial = {"inclusion_criteria": "", "exclusion_criteria": ""}
    id_map: dict[tuple[str, str], str] = {}
    for criterion_type in ("inclusion", "exclusion"):
        texts = []
        for row in pair_rows:
            if row["criterion_type"] != criterion_type or not reviewable(row):
                continue
            criterion_id = str(len(texts))
            texts.append(row["criterion_text"].strip())
            matching[criterion_type][criterion_id] = [
                row["gpt4_explanation"],
                json.loads(row["gpt4_sentences"]),
                row["gpt4_eligibility"],
            ]
            # JSON object keys are strings, so annotation IDs are stored as strings.
            id_map[(criterion_type, criterion_id)] = str(row["annotation_id"])
        trial[f"{criterion_type}_criteria"] = "\n\n".join(texts)
        # The agents look criteria up by TrialGPT's numbering; make sure it lines up.
        expected = {str(index): text for index, text in enumerate(texts)}
        if criteria_by_id(trial[f"{criterion_type}_criteria"]) != expected:
            raise ValueError(f"criterion numbering mismatch for {pair_key(pair_rows[0])} {criterion_type}")
    return matching, trial, pair_rows[0]["note"], id_map


# ---- running agents ------------------------------------------------------------

class CriteriaRun:
    def __init__(self, variant: str, model: str):
        model_safe = model.replace("/", "_")
        self.variant = variant
        self.model = model
        self.store = JsonStore(PROJECT_ROOT / "results" / f"criteria_{variant}_{model_safe}.json", indent=2)
        self.stop = threading.Event()
        self.stop_reason = ""
        self._lock = threading.Lock()
        self.errors = 0
        self.pairs_done = 0

    def process_patient(self, patient_pairs: list[list[dict]]) -> None:
        enhancer = build_enhancer(self.variant, self.model)
        for pair_rows in patient_pairs:
            if self.stop.is_set():
                return
            key = pair_key(pair_rows[0])
            try:
                self.process_pair(key, pair_rows, enhancer)
            except AllKeysExhausted as error:
                self.stop_reason = str(error)
                self.stop.set()
                return
            except Exception as error:
                with self._lock:
                    self.errors += 1
                print(f"[{key}] error: {str(error)[:200]}", flush=True)
                continue
            with self._lock:
                self.pairs_done += 1
            print(f"[{key}] reviewed {len(pair_rows)} criteria", flush=True)

    def process_pair(self, key: str, pair_rows: list[dict], enhancer) -> None:
        matching, trial, note, id_map = build_pair_input(pair_rows)
        with track_usage() as usage:
            enhanced, review = enhancer(matching, trial, note)
        records = {
            (item.get("criterion_type"), item.get("criterion_id")): item
            for item in review.get("criteria", [])
        }
        labels = {}
        for (criterion_type, criterion_id), annotation_id in id_map.items():
            prediction = enhanced[criterion_type][criterion_id]
            record = records.get((criterion_type, criterion_id), {})
            labels[annotation_id] = {
                "final_eligibility": prediction[2],
                "final_sentences": prediction[1],
                "decision": decision(record),
            }
        self.store.put(key, {"labels": labels, "usage": usage})


# ---- scoring -------------------------------------------------------------------

def _mcnemar_p(fixed: int, broken: int) -> float | None:
    """Exact two-sided McNemar p-value from the discordant pairs."""
    n = fixed + broken
    if n == 0:
        return None
    tail = sum(math.comb(n, k) for k in range(0, min(fixed, broken) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _prf(predicted: set, gold: set, counts: Counter) -> None:
    counts["tp"] += len(predicted & gold)
    counts["predicted"] += len(predicted)
    counts["gold"] += len(gold)


def score(rows: list[dict], store: dict) -> dict:
    outputs = {}
    usage = Counter()
    pairs_scored = set()
    for row in rows:
        stored = store.get(pair_key(row))
        if not isinstance(stored, dict):
            continue
        pairs_scored.add(pair_key(row))
        outputs[str(row["annotation_id"])] = stored["labels"].get(str(row["annotation_id"]))
    for key in pairs_scored:
        usage.update({k: v for k, v in store[key].get("usage", {}).items() if isinstance(v, (int, float))})

    scored = [row for row in rows if pair_key(row) in pairs_scored]
    baseline_ok = agent_ok = fixed = broken = changed = not_reviewed = 0
    transitions: Counter = Counter()
    transition_right: Counter = Counter()
    mistakes: Counter = Counter()
    mistakes_fixed: Counter = Counter()
    evidence = {"baseline": Counter(), "agents": Counter()}
    for row in scored:
        expert = row["expert_eligibility"]
        gpt4 = row["gpt4_eligibility"]
        output = outputs.get(str(row["annotation_id"]))
        if output is None:
            not_reviewed += 1
            final, final_sentences = gpt4, json.loads(row["gpt4_sentences"])
        else:
            final, final_sentences = output["final_eligibility"], output["final_sentences"]
        baseline_ok += gpt4 == expert
        agent_ok += final == expert
        fixed += gpt4 != expert and final == expert
        broken += gpt4 == expert and final != expert
        if final != gpt4:
            changed += 1
            transitions[(gpt4, final)] += 1
            transition_right[(gpt4, final)] += final == expert
        if gpt4 != expert:
            mistakes[(gpt4, expert)] += 1
            mistakes_fixed[(gpt4, expert)] += final == expert
        gold = set(json.loads(row["expert_sentences"]))
        _prf(set(json.loads(row["gpt4_sentences"])), gold, evidence["baseline"])
        _prf(set(final_sentences), gold, evidence["agents"])

    count = len(scored)

    def rate(value: int) -> float | None:
        return value / count if count else None

    def evidence_scores(counts: Counter) -> dict:
        return {
            "precision": counts["tp"] / counts["predicted"] if counts["predicted"] else None,
            "recall": counts["tp"] / counts["gold"] if counts["gold"] else None,
        }

    return {
        "selected": len(rows),
        "scored": count,
        "not_reviewed": not_reviewed,
        "pairs": len(pairs_scored),
        "baseline_accuracy": rate(baseline_ok),
        "agent_accuracy": rate(agent_ok),
        "fixed": fixed,
        "broken": broken,
        "changed": changed,
        "mcnemar_p": _mcnemar_p(fixed, broken),
        "transitions": [
            {"from": a, "to": b, "count": n, "right": transition_right[(a, b)]}
            for (a, b), n in transitions.most_common()
        ],
        "gpt4_mistakes": [
            {"gpt4": a, "expert": b, "count": n, "fixed": mistakes_fixed[(a, b)]}
            for (a, b), n in mistakes.most_common()
        ],
        "evidence": {name: evidence_scores(counts) for name, counts in evidence.items()},
        "usage": dict(usage),
        "tokens_per_criterion": usage["total_tokens"] / count if count else None,
    }


def _pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def print_report(report: dict, variant: str, label: str) -> None:
    print(f"\nCriterion-level evaluation: variant {variant}, {label}")
    print(f"  scored {report['scored']} of {report['selected']} criteria ({report['pairs']} patient-trial pairs)"
          + (f", {report['not_reviewed']} not reviewable (kept GPT-4 label)" if report["not_reviewed"] else ""))
    if not report["scored"]:
        return
    print(f"  accuracy vs physicians: GPT-4 baseline {_pct(report['baseline_accuracy'])}  ->  "
          f"with agents {_pct(report['agent_accuracy'])}")
    p = report["mcnemar_p"]
    print(f"  labels changed {report['changed']} | GPT-4 mistakes fixed {report['fixed']} | "
          f"correct labels broken {report['broken']} | net {report['fixed'] - report['broken']:+d}"
          + (f" | McNemar p={p:.3f}" if p is not None else ""))
    if report["transitions"]:
        print("  Changes made (GPT-4 label -> agent label: right / total):")
        for item in report["transitions"][:10]:
            print(f"    {item['from']:>22} -> {item['to']:<22} {item['right']:>3} / {item['count']}")
    if report["gpt4_mistakes"]:
        print("  GPT-4 mistakes (GPT-4 -> physician: fixed / total):")
        for item in report["gpt4_mistakes"][:10]:
            print(f"    {item['gpt4']:>22} -> {item['expert']:<22} {item['fixed']:>3} / {item['count']}")
    ev = report["evidence"]
    print(f"  evidence sentences vs physicians: GPT-4 precision {_pct(ev['baseline']['precision'])} "
          f"recall {_pct(ev['baseline']['recall'])} | agents precision {_pct(ev['agents']['precision'])} "
          f"recall {_pct(ev['agents']['recall'])}")
    usage = report["usage"]
    if usage.get("total_tokens"):
        print(f"  agent cost: {usage.get('calls', 0)} calls, {usage['total_tokens']:,} tokens "
              f"({report['tokens_per_criterion']:,.0f} per criterion), {usage.get('seconds', 0):.0f} API seconds")


# ---- main ----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    parser.add_argument("--sample", type=int, default=0, help="fixed subset of at least N criteria (0 = whole split)")
    parser.add_argument("--model", default=os.getenv("MODEL", "openai/gpt-oss-120b"))
    parser.add_argument("--workers", type=int, default=int(os.getenv("MAX_WORKERS", "3")))
    parser.add_argument("--max-minutes", type=float, default=0, help="stop after this many minutes; 0 = no limit")
    parser.add_argument("--report-only", action="store_true", help="score saved results without API calls")
    args = parser.parse_args()

    rows = select_rows(load_rows(), args.split, args.sample)
    label = f"split {args.split}" + (f" (sample {args.sample})" if args.sample else "")
    run = CriteriaRun(args.variant, args.model)
    build_enhancer(args.variant, args.model)  # fail fast on an unknown variant

    by_pair: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_pair[pair_key(row)].append(row)
    todo_by_patient: dict[str, list[list[dict]]] = defaultdict(list)
    for key, pair_rows in sorted(by_pair.items()):
        if run.store.get(key) is None:
            todo_by_patient[pair_rows[0]["patient_id"]].append(pair_rows)
    todo_pairs = sum(len(pairs) for pairs in todo_by_patient.values())

    print("=" * 70)
    print(f"Variant {args.variant} | model {args.model} | {label}")
    print(f"Criteria {len(rows)} in {len(by_pair)} pairs | pairs left to review {todo_pairs}")
    print("=" * 70, flush=True)

    status, code = "done", EXIT_DONE
    if todo_pairs and not args.report_only:
        pool = get_key_pool()
        started = time.time()
        deadline = started + args.max_minutes * 60 if args.max_minutes > 0 else None
        executor = ThreadPoolExecutor(max_workers=args.workers)
        pending = {executor.submit(run.process_patient, pairs) for pairs in todo_by_patient.values()}
        try:
            while pending:
                done, pending = wait(pending, timeout=5, return_when=FIRST_COMPLETED)
                for future in done:
                    future.result()
                if run.stop.is_set() or (deadline and time.time() >= deadline):
                    break
        except KeyboardInterrupt:
            print("\nInterrupted. Saved results are kept; re-run the same command to resume.", flush=True)
            os._exit(130)
        if run.stop.is_set():
            status, code = "daily_limit", EXIT_DAILY_LIMIT
        elif pending:
            run.stop.set()
            run.stop_reason = f"--max-minutes {args.max_minutes:g} reached; re-run to continue."
            status, code = "time_up", EXIT_TIME_UP
        print("\n" + "=" * 70)
        if run.stop_reason:
            print(f"Stopped: {run.stop_reason}")
        print(f"Ran {(time.time() - started) / 60:.1f} min | pairs reviewed: {run.pairs_done} | errors: {run.errors}")
        for item in pool.summary():
            print(f"  {item['key']}  requests {item['requests']:>4}  tokens {item['tokens']:>8,}  rate-limited {item['rate_limited']:>3}")
        if run.errors:
            print("Pairs with errors were not saved; the next run retries them.")
        if pending:
            # Workers may still be running; the file on disk is always complete.
            report = score(rows, json.loads(run.store.path.read_text()))
            print_report(report, args.variant, label)
            remaining = sum(1 for key in by_pair if run.store.get(key) is None)
            print(f"RESULT status={status} remaining_pairs={remaining} errors={run.errors}", flush=True)
            sys.stdout.flush()
            os._exit(code)
        executor.shutdown(wait=True)

    store = json.loads(run.store.path.read_text()) if run.store.path.exists() else {}
    report = score(rows, store)
    print_report(report, args.variant, label)
    model_safe = args.model.replace("/", "_")
    suffix = f"{args.split}" + (f"_sample{args.sample}" if args.sample else "")
    output = PROJECT_ROOT / "results" / f"criteria_eval_{args.variant}_{suffix}_{model_safe}.json"
    output.write_text(json.dumps(report, indent=2))
    print(f"\nSaved: {output.relative_to(PROJECT_ROOT)}")
    remaining = sum(1 for key in by_pair if store.get(key) is None)
    print(f"RESULT status={status} remaining_pairs={remaining} errors={run.errors}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
