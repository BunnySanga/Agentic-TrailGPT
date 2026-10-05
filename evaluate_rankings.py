#!/usr/bin/env python3
"""Score baseline vs enhanced trial rankings against the qrels ground truth.

Usage:
    python evaluate_rankings.py [--corpus sigir] [--model MODEL]
    python evaluate_rankings.py --variants baseline --patients-file ranking_dev_patients.txt

Only patients whose every retrieved trial has both a matching result and an
aggregation result in BOTH variants are scored, so the two variants are always
compared on the same patients. Trial score = TrialGPT matching score +
aggregation score (the official rank_results.py formula).

Token cost comes from results/usage_<corpus>_<model>.json, written by
run_parallel.py. Baseline = matching + baseline aggregation; enhanced =
matching + the three agents + enhanced aggregation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trialgpt_ranking.rank_results import get_agg_score, get_matching_score

K = 10
ELIGIBLE = 2
STAGES_BY_VARIANT = {
    "baseline": ("match", "agg-baseline"),
    "enhanced": ("match", "enhance", "agg-enhanced"),
}
USAGE_FIELDS = ("calls", "prompt_tokens", "completion_tokens", "total_tokens", "seconds")


def result_paths(corpus: str, model: str) -> dict[str, dict[str, Path]]:
    model_safe = model.replace("/", "_")
    results = PROJECT_ROOT / "results"
    return {
        "baseline": {
            "matching": results / f"matching_results_{corpus}_{model_safe}.json",
            "aggregation": results / f"aggregation_results_{corpus}_{model_safe}_baseline.json",
        },
        "enhanced": {
            "matching": results / f"matching_results_{corpus}_{model_safe}_enhanced.json",
            "aggregation": results / f"aggregation_results_{corpus}_{model_safe}_enhanced.json",
        },
    }


def load_qrels(corpus: str) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = {}
    with (PROJECT_ROOT / "dataset" / corpus / "qrels" / "test.tsv").open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            qrels.setdefault(row["query-id"], {})[row["corpus-id"]] = int(row["score"])
    return qrels


def load_candidates(corpus: str) -> dict[str, list[str]]:
    with (PROJECT_ROOT / "dataset" / corpus / "retrieved_trials.json").open() as handle:
        dataset = json.load(handle)
    return {
        item["patient_id"]: [trial["NCTID"] for label in ("2", "1", "0") for trial in item.get(label, [])]
        for item in dataset
    }


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as handle:
        return json.load(handle)


def _trial_results(matching: dict, patient_id: str) -> dict[str, dict]:
    flat: dict[str, dict] = {}
    for trials in matching.get(patient_id, {}).values():
        if isinstance(trials, dict):
            flat.update(trials)
    return flat


def rank_patient(
    patient_id: str,
    candidates: list[str],
    matching: dict,
    aggregation: dict,
) -> list[str] | None:
    """Rank one patient's trials, or None if any trial is missing a result."""
    trial_results = _trial_results(matching, patient_id)
    patient_agg = aggregation.get(patient_id, {})
    scores: dict[str, float] = {}
    for trial_id in candidates:
        result = trial_results.get(trial_id)
        assessment = patient_agg.get(trial_id)
        if not isinstance(result, dict) or not isinstance(assessment, dict):
            return None
        scores[trial_id] = get_matching_score(result) + get_agg_score(assessment)
    # Break ties by trial ID. The results files group trials by their
    # ground-truth label, so insertion order would leak the answer into ties.
    return sorted(scores, key=lambda trial_id: (-scores[trial_id], trial_id))


def ndcg_at_k(ranking: list[str], judgments: dict[str, int], k: int = K) -> float:
    def dcg(gains: list[int]) -> float:
        return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains[:k]))

    ideal = dcg(sorted(judgments.values(), reverse=True))
    if ideal == 0:
        return 0.0
    return dcg([judgments.get(trial_id, 0) for trial_id in ranking]) / ideal


def precision_at_k(ranking: list[str], judgments: dict[str, int], k: int = K) -> float:
    return sum(1 for trial_id in ranking[:k] if judgments.get(trial_id, 0) == ELIGIBLE) / k


def patient_cost(
    patient_usage: dict, trial_ids: list[str], variants: tuple[str, ...] = tuple(STAGES_BY_VARIANT)
) -> dict | None:
    """Sum token usage per variant for one patient, or None if any stage is unrecorded."""
    totals = {variant: dict.fromkeys(USAGE_FIELDS, 0) for variant in variants}
    for trial_id in trial_ids:
        stages = patient_usage.get(trial_id, {})
        for variant in variants:
            names = STAGES_BY_VARIANT[variant]
            for name in names:
                if not isinstance(stages.get(name), dict):
                    return None
                for field in USAGE_FIELDS:
                    totals[variant][field] += stages[name].get(field, 0)
    return totals


def _overhead_pct(baseline: float, enhanced: float) -> float | None:
    return (enhanced - baseline) / baseline * 100 if baseline else None


def cost_report(
    patient_ids: list[str],
    candidates: dict[str, list[str]],
    usage: dict,
    variants: tuple[str, ...] = tuple(STAGES_BY_VARIANT),
) -> dict:
    per_patient = {}
    for patient_id in patient_ids:
        cost = patient_cost(usage.get(patient_id, {}), candidates[patient_id], variants)
        if cost is not None:
            per_patient[patient_id] = {"trials": len(candidates[patient_id]), **cost}
            if "enhanced" in cost:
                per_patient[patient_id]["overhead_tokens_pct"] = _overhead_pct(
                    cost["baseline"]["total_tokens"], cost["enhanced"]["total_tokens"]
                )
    totals = {variant: dict.fromkeys(USAGE_FIELDS, 0) for variant in variants}
    for item in per_patient.values():
        for variant in variants:
            for field in USAGE_FIELDS:
                totals[variant][field] += item[variant][field]
    report = {
        "patients": len(per_patient),
        "trials": sum(item["trials"] for item in per_patient.values()),
        **totals,
        "per_patient": per_patient,
    }
    if "enhanced" in totals:
        report["overhead_tokens_pct"] = _overhead_pct(
            totals["baseline"]["total_tokens"], totals["enhanced"]["total_tokens"]
        )
    return report


def evaluate(
    corpus: str,
    model: str,
    variants: tuple[str, ...] = ("baseline", "enhanced"),
    patient_ids: list[str] | None = None,
) -> dict:
    """Score the given variants on patients complete in all of them.

    ``patient_ids`` limits scoring to those patients (e.g. a dev or test list).
    """
    qrels = load_qrels(corpus)
    candidates = load_candidates(corpus)
    if patient_ids is not None:
        wanted = set(patient_ids)
        candidates = {patient_id: trials for patient_id, trials in candidates.items() if patient_id in wanted}
    paths = {variant: files for variant, files in result_paths(corpus, model).items() if variant in variants}
    loaded = {
        variant: (_load(files["matching"]), _load(files["aggregation"]))
        for variant, files in paths.items()
    }

    rankings: dict[str, dict[str, list[str]]] = {variant: {} for variant in paths}
    for patient_id, trial_ids in candidates.items():
        per_variant = {
            variant: rank_patient(patient_id, trial_ids, matching, aggregation)
            for variant, (matching, aggregation) in loaded.items()
        }
        if all(ranking is not None for ranking in per_variant.values()):
            for variant, ranking in per_variant.items():
                rankings[variant][patient_id] = ranking

    report: dict = {"corpus": corpus, "model": model, "k": K, "variants": {}}
    usage = _load(PROJECT_ROOT / "results" / f"usage_{corpus}_{model.replace('/', '_')}.json")
    report["cost"] = cost_report(sorted(rankings["baseline"]), candidates, usage, tuple(paths))
    for variant, by_patient in rankings.items():
        per_patient = {
            patient_id: {
                f"ndcg@{K}": ndcg_at_k(ranking, qrels.get(patient_id, {})),
                f"p@{K}": precision_at_k(ranking, qrels.get(patient_id, {})),
            }
            for patient_id, ranking in by_patient.items()
        }
        count = len(per_patient)
        report["variants"][variant] = {
            "patients": count,
            f"ndcg@{K}": sum(item[f"ndcg@{K}"] for item in per_patient.values()) / count if count else None,
            f"p@{K}": sum(item[f"p@{K}"] for item in per_patient.values()) / count if count else None,
            "per_patient": per_patient,
        }
    return report


def print_report(report: dict) -> None:
    variants = report["variants"]
    count = next(iter(variants.values()))["patients"] if variants else 0
    print(f"\nRanking evaluation ({report['corpus']}, {report['model']}) on {count} complete patients")
    if not count:
        print(f"  No patient has complete results for: {', '.join(variants)}.")
        return
    print(f"  {'variant':<10} {'NDCG@10':>8} {'P@10':>8}")
    for variant, scores in variants.items():
        print(f"  {variant:<10} {scores[f'ndcg@{K}']:>8.4f} {scores[f'p@{K}']:>8.4f}")
    print("  (P@10 counts eligible trials, qrels label 2. NDCG@10 uses graded labels 0-2.)")

    cost = report.get("cost") or {}
    if not cost.get("patients"):
        print("\nToken cost: no patient has usage recorded for every stage yet.")
        return
    print(f"\nToken cost on {cost['patients']} patients ({cost['trials']} trials)")
    print(f"  {'variant':<10} {'calls':>6} {'input':>10} {'output':>10} {'total':>10} {'per trial':>10} {'API secs':>9}")
    for variant in variants:
        item = cost[variant]
        print(f"  {variant:<10} {item['calls']:>6} {item['prompt_tokens']:>10,} {item['completion_tokens']:>10,} "
              f"{item['total_tokens']:>10,} {item['total_tokens'] / cost['trials']:>10,.0f} {item['seconds']:>9.0f}")
    if cost.get("overhead_tokens_pct") is not None:
        print(f"  The agents add {cost['overhead_tokens_pct']:+.0f}% tokens.")
    print("  (baseline = matching + aggregation; enhanced = matching + agents + aggregation)")

    print("\nPer patient")
    header = f"  {'patient':<14} {'trials':>6}" + "".join(f" {'NDCG ' + v[:4]:>9} {'P@10 ' + v[:4]:>9}" for v in variants)
    print(header + "".join(f" {'tokens ' + v[:4]:>12}" for v in variants))
    for patient_id, item in cost["per_patient"].items():
        line = f"  {patient_id:<14} {item['trials']:>6}"
        for variant in variants:
            scores = variants[variant]["per_patient"][patient_id]
            line += f" {scores[f'ndcg@{K}']:>9.4f} {scores[f'p@{K}']:>9.2f}"
        line += "".join(f" {item[variant]['total_tokens']:>12,}" for variant in variants)
        print(line)


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", default="sigir")
    parser.add_argument("--model", default=os.getenv("MODEL", "openai/gpt-oss-120b"))
    parser.add_argument("--variants", default="baseline,enhanced", help="comma-separated: baseline, enhanced")
    parser.add_argument("--patients-file", type=Path, help="score only the patients listed in this file")
    args = parser.parse_args()

    variants = tuple(variant.strip() for variant in args.variants.split(",") if variant.strip())
    unknown = set(variants) - set(STAGES_BY_VARIANT)
    if unknown:
        raise SystemExit(f"Unknown variants: {', '.join(sorted(unknown))}")
    patient_ids = None
    if args.patients_file:
        from run_parallel import read_patients_file

        patient_ids = read_patients_file(args.patients_file)

    report = evaluate(args.corpus, args.model, variants=variants, patient_ids=patient_ids)
    print_report(report)

    suffix = "_".join(variants) + (f"_{args.patients_file.stem}" if args.patients_file else "")
    output = PROJECT_ROOT / "results" / f"evaluation_{args.corpus}_{args.model.replace('/', '_')}_{suffix}.json"
    with output.open("w") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nSaved: {output.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
