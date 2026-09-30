"""Show the detailed results of agent-processed trials."""
import json

review = json.load(open("results/matching_results_sigir_qwen_qwen3.8-27b_enhanced_review.json"))
baseline = json.load(open("results/matching_results_sigir_qwen_qwen3.8-27b.json"))
enhanced = json.load(open("results/matching_results_sigir_qwen_qwen3.8-27b_enhanced.json"))

print("=" * 70)
print("AGENTIC-TRAILGPT — AGENT PROCESSING RESULTS")
print("=" * 70)

for pid, trials in review.items():
    for tid, data in trials.items():
        if not isinstance(data, dict) or "criteria" not in data:
            continue
        criteria = data["criteria"]
        print(f"\nPatient: {pid}")
        print(f"Trial: {tid}")
        print(f"Criteria reviewed by agents: {len(criteria)}")
        print("-" * 70)

        changes = []
        for c in criteria:
            initial = c.get("initial_eligibility")
            final = c.get("final_eligibility")
            ctype = c.get("criterion_type", "?")
            cid = c.get("criterion_id", "?")
            criterion_text = c.get("criterion", "")[:80]
            verd = c.get("verifier", {}).get("verdict", "N/A")
            support = c.get("verifier", {}).get("support_level", "N/A")
            issues = c.get("verifier", {}).get("issues", [])
            clar_triggered = c.get("clarification", {}).get("triggered", False)
            assertion = c.get("assertion", {})
            all_sents = assertion.get("sentence_assertions", [])
            usable_ids = assertion.get("usable_sentence_ids", [])
            filtered = len(all_sents) - len(usable_ids)

            changed = initial != final
            marker = "  ** CORRECTED **" if changed else ""

            print(f"\n  [{ctype}:{cid}] {criterion_text}")
            print(f"    Baseline label:  {initial}")
            print(f"    Enhanced label:  {final}{marker}")
            print(f"    Verifier:        {verd} (support: {support})")
            if issues:
                for issue in issues[:2]:
                    print(f"    Issue:           {issue}")
            print(f"    Assertion:       {len(all_sents)} sentences checked, {len(usable_ids)} usable, {filtered} filtered")
            if clar_triggered:
                print(f"    Clarification:   TRIGGERED - found additional evidence")
            if changed:
                changes.append({
                    "type": ctype,
                    "id": cid,
                    "criterion": criterion_text,
                    "before": initial,
                    "after": final,
                    "verdict": verd,
                    "issues": issues,
                })

        print("\n" + "=" * 70)
        print(f"SUMMARY: {len(changes)} corrections out of {len(criteria)} criteria")
        if changes:
            print("\nCORRECTIONS MADE:")
            for i, ch in enumerate(changes, 1):
                print(f"  {i}. [{ch['type']}:{ch['id']}] {ch['criterion']}")
                print(f"     {ch['before']} -> {ch['after']} (verifier: {ch['verdict']})")
                for issue in ch["issues"][:2]:
                    print(f"     Reason: {issue}")
        print("=" * 70)

# Also show baseline stats
print("\n\nBASELINE MATCHING STATS (all 3 patients)")
print("-" * 40)
total_criteria = 0
label_counts = {}
for pid in ["sigir-20141", "sigir-20142", "sigir-20144"]:
    if pid not in baseline:
        continue
    for label_key in ["0", "1", "2"]:
        for tid, result in baseline[pid].get(label_key, {}).items():
            if not isinstance(result, dict):
                continue
            for ctype in ["inclusion", "exclusion"]:
                if ctype not in result or not isinstance(result[ctype], dict):
                    continue
                for cid, pred in result[ctype].items():
                    if isinstance(pred, list) and len(pred) == 3:
                        total_criteria += 1
                        label = pred[2]
                        label_counts[label] = label_counts.get(label, 0) + 1

print(f"Total criteria evaluated: {total_criteria}")
for label in sorted(label_counts.keys()):
    pct = label_counts[label] / total_criteria * 100
    print(f"  {label:30s}: {label_counts[label]:4d} ({pct:.1f}%)")
