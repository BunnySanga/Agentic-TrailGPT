#!/usr/bin/env python3
"""
Compare baseline TrialGPT vs Agentic-TrailGPT (enhanced) results.
Shows which criteria were corrected by the agents and why.
"""

import json
import sys
import csv
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

MODEL = os.getenv("MODEL", "qwen/qwen3.8-27b")
MODEL_SAFE = MODEL.replace("/", "_")


def load_ground_truth(corpus):
    """Load ground truth relevance labels."""
    gt = {}
    gt_path = Path(f"dataset/{corpus}/qrels/test.tsv")
    with gt_path.open() as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for row in reader:
            patient_id, trial_id, score = row[0], row[1], int(row[2])
            gt.setdefault(patient_id, {})[trial_id] = score
    return gt


def count_labels(matching_result):
    """Count criterion-level labels in a matching result."""
    counts = {}
    for ctype in ["inclusion", "exclusion"]:
        if ctype not in matching_result or not isinstance(matching_result[ctype], dict):
            continue
        for cid, pred in matching_result[ctype].items():
            if isinstance(pred, list) and len(pred) == 3:
                label = pred[2]
                counts[label] = counts.get(label, 0) + 1
    return counts


def find_corrections(baseline, enhanced, review_data):
    """Find criteria where agents changed the label."""
    corrections = []
    if not review_data or "criteria" not in review_data:
        return corrections
    for criterion_review in review_data["criteria"]:
        initial = criterion_review.get("initial_eligibility")
        final = criterion_review.get("final_eligibility")
        if initial != final:
            corrections.append({
                "criterion_type": criterion_review.get("criterion_type"),
                "criterion_id": criterion_review.get("criterion_id"),
                "criterion": criterion_review.get("criterion", "")[:100],
                "initial_label": initial,
                "final_label": final,
                "verifier_verdict": criterion_review.get("verifier", {}).get("verdict"),
                "verifier_support": criterion_review.get("verifier", {}).get("support_level"),
                "issues": criterion_review.get("verifier", {}).get("issues", []),
                "assertion_filtered": _count_filtered(criterion_review.get("assertion", {})),
                "clarification_triggered": criterion_review.get("clarification", {}).get("triggered", False),
            })
    return corrections


def _count_filtered(assertion):
    """Count how many sentences were filtered by assertion agent."""
    assertions = assertion.get("sentence_assertions", [])
    if not isinstance(assertions, list):
        return 0
    return sum(1 for a in assertions if isinstance(a, dict) and not a.get("usable_as_patient_evidence", True))


def main():
    if len(sys.argv) < 4:
        print("Usage: python compare_results.py <baseline.json> <enhanced.json> <review.json>")
        return 1

    baseline_path = Path(sys.argv[1])
    enhanced_path = Path(sys.argv[2])
    review_path = Path(sys.argv[3])

    if not baseline_path.exists():
        print(f"Baseline results not found: {baseline_path}")
        return 1

    baseline = json.load(baseline_path.open())

    if enhanced_path.exists():
        enhanced = json.load(enhanced_path.open())
    else:
        print(f"Enhanced results not found: {enhanced_path}")
        print("Run the enhancement step first.")
        enhanced = None

    if review_path.exists():
        review = json.load(review_path.open())
    else:
        review = {}

    # Load ground truth
    gt = load_ground_truth("sigir")

    print("=" * 70)
    print("BASELINE vs AGENTIC-TRAILGPT COMPARISON")
    print("=" * 70)

    total_criteria_baseline = 0
    total_criteria_enhanced = 0
    total_corrections = 0
    all_corrections = []
    baseline_label_dist = {}
    enhanced_label_dist = {}
    assertion_filtered_total = 0
    clarification_triggered_total = 0
    verifier_verdicts = {}

    for patient_id in baseline:
        for label_key in ["0", "1", "2"]:
            trials = baseline[patient_id].get(label_key, {})
            for trial_id, result in trials.items():
                if not isinstance(result, dict):
                    continue

                # Count baseline labels
                bl = count_labels(result)
                for k, v in bl.items():
                    baseline_label_dist[k] = baseline_label_dist.get(k, 0) + v
                    total_criteria_baseline += v

                # Count enhanced labels
                if enhanced and patient_id in enhanced:
                    enh_result = enhanced.get(patient_id, {}).get(label_key, {}).get(trial_id)
                    if enh_result and isinstance(enh_result, dict):
                        el = count_labels(enh_result)
                        for k, v in el.items():
                            enhanced_label_dist[k] = enhanced_label_dist.get(k, 0) + v
                            total_criteria_enhanced += v

                # Find corrections from review
                review_data = review.get(patient_id, {}).get(trial_id)
                if review_data:
                    corrections = find_corrections(result, None, review_data)
                    all_corrections.extend(corrections)
                    total_corrections += len(corrections)
                    for c in corrections:
                        assertion_filtered_total += c["assertion_filtered"]
                        if c["clarification_triggered"]:
                            clarification_triggered_total += 1
                        v = c["verifier_verdict"]
                        verifier_verdicts[v] = verifier_verdicts.get(v, 0) + 1

    # Print summary
    print(f"\nPatients processed: {len(baseline)}")
    print(f"Total criterion decisions (baseline): {total_criteria_baseline}")

    print(f"\n--- BASELINE LABEL DISTRIBUTION ---")
    for label in sorted(baseline_label_dist.keys()):
        count = baseline_label_dist[label]
        pct = count / max(total_criteria_baseline, 1) * 100
        print(f"  {label:30s}: {count:4d} ({pct:.1f}%)")

    if enhanced_label_dist:
        print(f"\n--- ENHANCED LABEL DISTRIBUTION ---")
        for label in sorted(enhanced_label_dist.keys()):
            count = enhanced_label_dist[label]
            pct = count / max(total_criteria_enhanced, 1) * 100
            print(f"  {label:30s}: {count:4d} ({pct:.1f}%)")

    print(f"\n--- AGENT ACTIVITY ---")
    print(f"  Total corrections by agents: {total_corrections}")
    print(f"  Sentences filtered by Assertion Agent: {assertion_filtered_total}")
    print(f"  Clarification Agent triggered: {clarification_triggered_total} times")
    print(f"  Verifier verdicts:")
    for verdict, count in sorted(verifier_verdicts.items(), key=lambda x: -x[1]):
        print(f"    {verdict}: {count}")

    if all_corrections:
        print(f"\n--- SAMPLE CORRECTIONS (showing up to 10) ---")
        for i, c in enumerate(all_corrections[:10], 1):
            print(f"\n  Correction {i}:")
            print(f"    Type: {c['criterion_type']}")
            print(f"    Criterion: {c['criterion']}")
            print(f"    BEFORE: {c['initial_label']}")
            print(f"    AFTER:  {c['final_label']}")
            print(f"    Verifier: {c['verifier_verdict']} (support: {c['verifier_support']})")
            if c['issues']:
                print(f"    Issues: {'; '.join(c['issues'][:2])}")
            if c['assertion_filtered'] > 0:
                print(f"    Assertion filtered {c['assertion_filtered']} unusable sentences")
            if c['clarification_triggered']:
                print(f"    Clarification Agent found additional evidence")

    # Save comparison
    comparison = {
        "patients_processed": len(baseline),
        "total_criteria_baseline": total_criteria_baseline,
        "total_criteria_enhanced": total_criteria_enhanced,
        "baseline_label_distribution": baseline_label_dist,
        "enhanced_label_distribution": enhanced_label_dist,
        "total_corrections": total_corrections,
        "assertion_filtered_sentences": assertion_filtered_total,
        "clarification_triggered": clarification_triggered_total,
        "verifier_verdicts": verifier_verdicts,
        "corrections": all_corrections,
    }

    out_path = f"results/comparison_sigir_{MODEL_SAFE}.json"
    with open(out_path, "w") as f:
        json.dump(comparison, f, indent=2)
    print(f"\nFull comparison saved to: {out_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
