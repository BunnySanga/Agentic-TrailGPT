#!/usr/bin/env python3
"""Score TrialGPT's trial rankings, with and without the Reviewer, against the qrels.

Usage:
    python evaluate_rankings.py --variants baseline --patients-file ranking_dev_patients.txt
    python evaluate_rankings.py --patients-file ranking_dev_patients.txt --penalty 0.5 --weight 2
    python evaluate_rankings.py --patients-file ranking_dev_patients.txt --grid
    python evaluate_rankings.py --patients-file ranking_dev_patients.txt --min-relevance 60
    python evaluate_rankings.py --patients-file ranking_test_patients.txt --patients-file ranking_test_extra_patients.txt

Variants:
    baseline  TrialGPT matching + TrialGPT aggregation
    reviewed  the same, after the Reviewer re-checked negative labels on relevant trials

Trials are ranked by agentic_score.trial_score: TrialGPT's formula with an
adjustable --penalty per negative label and --weight on (R+E)/100. With
--penalty 1 --weight 1 (the defaults) it equals TrialGPT's rank_results.py.
Tune --penalty, --weight and --min-relevance on the development patients
only; the held-out patients are scored once, at the end.

Only patients whose every retrieved trial has results in ALL requested variants
are scored, so variants are compared on the same patients. Token cost comes
from results/usage_<corpus>_<model>.json, written by run_parallel.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agentic_score import trial_score

K = 10
ELIGIBLE = 2
STAGES_BY_VARIANT = {
    "baseline": ("match", "agg-baseline"),
    "reviewed": ("match", "agg-baseline", "review"),
}
USAGE_FIELDS = ("calls", "prompt_tokens", "completion_tokens", "total_tokens", "seconds")
GRID_PENALTIES = (1.0, 0.75, 0.5, 0.25, 0.0)
GRID_WEIGHTS = (1.0, 1.5, 2.0, 3.0)
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 2024


def result_paths(corpus: str, model: str) -> dict[str, Path]:
    model_safe = model.replace("/", "_")
    results = PROJECT_ROOT / "results"
    return {
        "matching": results / f"matching_results_{corpus}_{model_safe}.json",
        "reviewed": results / f"matching_results_{corpus}_{model_safe}_reviewed.json",
        "review_log": results / f"review_{corpus}_{model_safe}.json",
        "aggregation": results / f"aggregation_results_{corpus}_{model_safe}_baseline.json",
        "usage": results / f"usage_{corpus}_{model_safe}.json",
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
    """Flatten {label: {trial_id: result}} into {trial_id: result} for one patient."""
    flat: dict[str, dict] = {}
    for trials in matching.get(patient_id, {}).values():
        if isinstance(trials, dict):
            flat.update(trials)
    return flat


# ---- ranking ----------------------------------------------------------------------

def rank_trials(
    candidates: list[str],
    trial_results: dict[str, dict],
    assessments: dict[str, dict],
    penalty: float = 1.0,
    weight: float = 1.0,
) -> list[str] | None:
    """Rank one patient's trials, or None if any trial is missing a result."""
    scores: dict[str, float] = {}
    for trial_id in candidates:
        result = trial_results.get(trial_id)
        assessment = assessments.get(trial_id)
        if not isinstance(result, dict) or not isinstance(assessment, dict):
            return None
        scores[trial_id] = trial_score(result, assessment, penalty, weight)
    # Break ties by trial ID. The results files group trials by their
    # ground-truth label, so insertion order would leak the answer into ties.
    return sorted(scores, key=lambda trial_id: (-scores[trial_id], trial_id))


def rank_patient(
    patient_id: str,
    candidates: list[str],
    matching: dict,
    aggregation: dict,
    penalty: float = 1.0,
    weight: float = 1.0,
) -> list[str] | None:
    """Rank one patient's trials from TrialGPT-shaped matching and aggregation results."""
    return rank_trials(candidates, _trial_results(matching, patient_id), aggregation.get(patient_id, {}), penalty, weight)


def ndcg_at_k(ranking: list[str], judgments: dict[str, int], k: int = K) -> float:
    def dcg(gains: list[int]) -> float:
        return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains[:k]))

    ideal = dcg(sorted(judgments.values(), reverse=True))
    if ideal == 0:
        return 0.0
    return dcg([judgments.get(trial_id, 0) for trial_id in ranking]) / ideal


def precision_at_k(ranking: list[str], judgments: dict[str, int], k: int = K) -> float:
    return sum(1 for trial_id in ranking[:k] if judgments.get(trial_id, 0) == ELIGIBLE) / k


# ---- the Reviewer's results -------------------------------------------------------

def review_applies(record: dict, min_relevance: float | None) -> bool:
    """Whether the Reviewer's labels count for a trial at this relevance cutoff.

    ``min_relevance=None`` uses the cutoff the review was run with. A higher
    cutoff is simulated by ignoring reviews of trials below it; a lower one
    cannot be, because those trials were never reviewed.
    """
    if min_relevance is not None and record.get("min_relevance", 0) > min_relevance:
        raise SystemExit(
            f"The review ran with --min-relevance {record['min_relevance']:g}; "
            f"it cannot be scored at {min_relevance:g}. Re-run the review with a lower cutoff."
        )
    if not record.get("selected"):
        return False
    return min_relevance is None or (record.get("relevance") or 0) >= min_relevance


def reviewed_trial_results(
    patient_id: str,
    candidates: list[str],
    matching: dict,
    reviewed: dict,
    review_log: dict,
    min_relevance: float | None,
) -> tuple[dict[str, dict], set[str]] | None:
    """Per-trial matching after the Reviewer, plus the trials whose review counts.

    None if any trial has no review record yet.
    """
    baseline, after = _trial_results(matching, patient_id), _trial_results(reviewed, patient_id)
    records = review_log.get(patient_id, {})
    results: dict[str, dict] = {}
    applied: set[str] = set()
    for trial_id in candidates:
        record = records.get(trial_id)
        if not isinstance(record, dict):
            return None
        if review_applies(record, min_relevance):
            results[trial_id] = after.get(trial_id)
            applied.add(trial_id)
        else:
            results[trial_id] = baseline.get(trial_id)
    return results, applied


# ---- cost ---------------------------------------------------------------------------

def patient_cost(
    patient_usage: dict,
    trial_ids: list[str],
    variants: tuple[str, ...] = tuple(STAGES_BY_VARIANT),
    reviewed_trials: set[str] | None = None,
) -> dict | None:
    """Sum token usage per variant for one patient, or None if any stage is unrecorded.

    ``reviewed_trials`` limits the Reviewer's cost to the trials whose review
    counts (when a higher relevance cutoff is simulated).
    """
    totals = {variant: dict.fromkeys(USAGE_FIELDS, 0) for variant in variants}
    for trial_id in trial_ids:
        stages = patient_usage.get(trial_id, {})
        for variant in variants:
            for name in STAGES_BY_VARIANT[variant]:
                if not isinstance(stages.get(name), dict):
                    return None
                if name == "review" and reviewed_trials is not None and trial_id not in reviewed_trials:
                    continue
                for field in USAGE_FIELDS:
                    totals[variant][field] += stages[name].get(field, 0)
    return totals


def _overhead_pct(baseline: float, reviewed: float) -> float | None:
    return (reviewed - baseline) / baseline * 100 if baseline else None


def cost_report(
    patient_ids: list[str],
    candidates: dict[str, list[str]],
    usage: dict,
    variants: tuple[str, ...] = tuple(STAGES_BY_VARIANT),
    reviewed_trials: dict[str, set[str]] | None = None,
) -> dict:
    per_patient = {}
    for patient_id in patient_ids:
        cost = patient_cost(
            usage.get(patient_id, {}), candidates[patient_id], variants,
            None if reviewed_trials is None else reviewed_trials.get(patient_id, set()),
        )
        if cost is not None:
            per_patient[patient_id] = {"trials": len(candidates[patient_id]), **cost}
            if "baseline" in cost and "reviewed" in cost:
                per_patient[patient_id]["overhead_tokens_pct"] = _overhead_pct(
                    cost["baseline"]["total_tokens"], cost["reviewed"]["total_tokens"]
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
    if "baseline" in totals and "reviewed" in totals:
        report["overhead_tokens_pct"] = _overhead_pct(
            totals["baseline"]["total_tokens"], totals["reviewed"]["total_tokens"]
        )
    return report


# ---- evaluation ---------------------------------------------------------------------

def _variant_inputs(
    variant: str, patient_id: str, candidates: list[str], files: dict, min_relevance: float | None
) -> tuple[dict[str, dict], set[str]] | None:
    if variant == "baseline":
        return _trial_results(files["matching"], patient_id), set()
    return reviewed_trial_results(
        patient_id, candidates, files["matching"], files["reviewed"], files["review_log"], min_relevance
    )


def _scores(rankings: dict[str, list[str]], qrels: dict) -> dict:
    per_patient = {
        patient_id: {
            f"ndcg@{K}": ndcg_at_k(ranking, qrels.get(patient_id, {})),
            f"p@{K}": precision_at_k(ranking, qrels.get(patient_id, {})),
        }
        for patient_id, ranking in rankings.items()
    }
    count = len(per_patient)
    return {
        "patients": count,
        f"ndcg@{K}": sum(item[f"ndcg@{K}"] for item in per_patient.values()) / count if count else None,
        f"p@{K}": sum(item[f"p@{K}"] for item in per_patient.values()) / count if count else None,
        "per_patient": per_patient,
    }


def paired_comparison(reference: dict, other: dict, metric: str = f"ndcg@{K}") -> dict:
    """Per-patient comparison of two scored runs: mean difference, wins, and a bootstrap 95% CI."""
    patients = sorted(set(reference) & set(other))
    diffs = [other[patient_id][metric] - reference[patient_id][metric] for patient_id in patients]
    if not diffs:
        return {"patients": 0}
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(
        sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(BOOTSTRAP_SAMPLES)
    )
    return {
        "patients": len(diffs),
        "metric": metric,
        "mean_difference": sum(diffs) / len(diffs),
        "better": sum(1 for diff in diffs if diff > 1e-12),
        "same": sum(1 for diff in diffs if abs(diff) <= 1e-12),
        "worse": sum(1 for diff in diffs if diff < -1e-12),
        "ci95": [means[int(0.025 * BOOTSTRAP_SAMPLES)], means[int(0.975 * BOOTSTRAP_SAMPLES) - 1]],
    }


def evaluate(
    corpus: str,
    model: str,
    variants: tuple[str, ...] = ("baseline", "reviewed"),
    patient_ids: list[str] | None = None,
    penalty: float = 1.0,
    weight: float = 1.0,
    min_relevance: float | None = None,
    grid: bool = False,
) -> dict:
    """Score the given variants on the patients complete in all of them.

    ``patient_ids`` limits scoring to those patients (e.g. a dev or test list).
    """
    qrels = load_qrels(corpus)
    candidates = load_candidates(corpus)
    if patient_ids is not None:
        wanted = set(patient_ids)
        candidates = {patient_id: trials for patient_id, trials in candidates.items() if patient_id in wanted}
    files = {name: _load(path) for name, path in result_paths(corpus, model).items()}

    inputs: dict[str, dict[str, tuple[dict, set[str]]]] = {variant: {} for variant in variants}
    for patient_id, trial_ids in candidates.items():
        assessments = files["aggregation"].get(patient_id, {})
        per_variant = {
            variant: _variant_inputs(variant, patient_id, trial_ids, files, min_relevance) for variant in variants
        }
        if all(
            item is not None and rank_trials(trial_ids, item[0], assessments) is not None
            for item in per_variant.values()
        ):
            for variant, item in per_variant.items():
                inputs[variant][patient_id] = item

    def rank_all(variant: str, p: float, w: float) -> dict[str, list[str]]:
        return {
            patient_id: rank_trials(candidates[patient_id], results, files["aggregation"][patient_id], p, w)
            for patient_id, (results, _) in inputs[variant].items()
        }

    report: dict = {
        "corpus": corpus, "model": model, "k": K,
        "score": {"penalty": penalty, "weight": weight}, "min_relevance": min_relevance,
        "variants": {variant: _scores(rank_all(variant, penalty, weight), qrels) for variant in variants},
    }
    # Everything is compared with TrialGPT as published: baseline, TrialGPT's formula.
    if "baseline" in variants:
        trialgpt = (
            report["variants"]["baseline"] if (penalty, weight) == (1.0, 1.0)
            else _scores(rank_all("baseline", 1.0, 1.0), qrels)
        )
        report["trialgpt"] = {key: value for key, value in trialgpt.items() if key != "per_patient"}
        report["comparisons"] = {
            variant: {
                metric: paired_comparison(trialgpt["per_patient"], scores["per_patient"], metric)
                for metric in (f"ndcg@{K}", f"p@{K}")
            }
            for variant, scores in report["variants"].items()
            if not (variant == "baseline" and (penalty, weight) == (1.0, 1.0))
        }
    # Every variant is ranked on the same patients, so any variant's keys will do.
    ranked_patients = sorted(next(iter(inputs.values()), {}))
    reviewed_trials = (
        {patient_id: applied for patient_id, (_, applied) in inputs["reviewed"].items()}
        if "reviewed" in inputs and min_relevance is not None else None
    )
    report["cost"] = cost_report(ranked_patients, candidates, files["usage"], variants, reviewed_trials)
    if grid:
        report["grid"] = [
            {
                "penalty": p,
                "weight": w,
                **{
                    variant: {key: value for key, value in _scores(rank_all(variant, p, w), qrels).items()
                              if key != "per_patient"}
                    for variant in variants
                },
            }
            for p in GRID_PENALTIES
            for w in GRID_WEIGHTS
        ]
    return report


def print_report(report: dict) -> None:
    variants = report["variants"]
    count = next(iter(variants.values()))["patients"] if variants else 0
    score = report.get("score", {"penalty": 1.0, "weight": 1.0})
    print(f"\nRanking evaluation ({report['corpus']}, {report['model']}) on {count} complete patients")
    print(f"  score: penalty {score['penalty']:g} per negative label, weight {score['weight']:g} on (R+E)/100"
          + ("  (TrialGPT's formula)" if score == {"penalty": 1.0, "weight": 1.0} else ""))
    if report.get("min_relevance") is not None:
        print(f"  Reviewer counted only on trials with R >= {report['min_relevance']:g}")
    if not count:
        print(f"  No patient has complete results for: {', '.join(variants)}.")
        return
    print(f"  {'variant':<10} {'NDCG@10':>8} {'P@10':>8}")
    for variant, scores in variants.items():
        print(f"  {variant:<10} {scores[f'ndcg@{K}']:>8.4f} {scores[f'p@{K}']:>8.4f}")
    print("  (P@10 counts eligible trials, qrels label 2. NDCG@10 uses graded labels 0-2.)")

    if report.get("comparisons"):
        reference = report["trialgpt"]
        print(f"\nAgainst TrialGPT as published (NDCG@10 {reference[f'ndcg@{K}']:.4f}, P@10 {reference[f'p@{K}']:.4f}):")
        for variant, metrics in report["comparisons"].items():
            for metric, item in metrics.items():
                if not item.get("patients"):
                    continue
                low, high = item["ci95"]
                print(f"  {variant:<10} {metric:<8} {item['mean_difference']:+.4f} (95% CI {low:+.4f} to {high:+.4f}); "
                      f"better for {item['better']}, same {item['same']}, worse {item['worse']} of {item['patients']} patients")

    if report.get("grid"):
        print("\nScore grid, NDCG@10 / P@10")
        for row in report["grid"]:
            cells = "  ".join(
                f"{variant} {row[variant][f'ndcg@{K}']:.4f} / {row[variant][f'p@{K}']:.4f}" for variant in variants
            )
            print(f"  penalty {row['penalty']:<5g} weight {row['weight']:<4g} {cells}")

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
        print(f"  The Reviewer adds {cost['overhead_tokens_pct']:+.1f}% tokens.")
    print("  (baseline = matching + aggregation; reviewed = baseline + Reviewer)")

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
    parser.add_argument("--variants", default="baseline,reviewed", help="comma-separated: baseline, reviewed")
    parser.add_argument("--patients-file", type=Path, action="append",
                        help="score only the patients listed in this file (repeat to combine lists)")
    parser.add_argument("--penalty", type=float, default=1.0, help="score lost per negative label (TrialGPT: 1)")
    parser.add_argument("--weight", type=float, default=1.0, help="weight on (R+E)/100 (TrialGPT: 1)")
    parser.add_argument("--min-relevance", type=float, default=None,
                        help="count the Reviewer only on trials with R at least this (default: as it was run)")
    parser.add_argument("--grid", action="store_true", help="also score a grid of penalties and weights")
    args = parser.parse_args()

    variants = tuple(variant.strip() for variant in args.variants.split(",") if variant.strip())
    unknown = set(variants) - set(STAGES_BY_VARIANT)
    if unknown:
        raise SystemExit(f"Unknown variants: {', '.join(sorted(unknown))}")
    patient_ids = None
    if args.patients_file:
        from run_parallel import read_patients_file

        patient_ids = [patient_id for path in args.patients_file for patient_id in read_patients_file(path)]

    report = evaluate(
        args.corpus, args.model, variants=variants, patient_ids=patient_ids,
        penalty=args.penalty, weight=args.weight, min_relevance=args.min_relevance, grid=args.grid,
    )
    print_report(report)

    suffix = "_".join(variants) + "".join(f"_{path.stem}" for path in args.patients_file or [])
    if (args.penalty, args.weight) != (1.0, 1.0):
        suffix += f"_p{args.penalty:g}_w{args.weight:g}"
    if args.min_relevance is not None:
        suffix += f"_r{args.min_relevance:g}"
    if args.grid:
        suffix += "_grid"
    output = PROJECT_ROOT / "results" / f"evaluation_{args.corpus}_{args.model.replace('/', '_')}_{suffix}.json"
    with output.open("w") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nSaved: {output.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
