import json

review = json.load(open('results/matching_results_sigir_qwen_qwen3.8-27b_enhanced_review.json'))

total_criteria = 0
assertion_filtered = 0
assertion_total_sentences = 0
clarification_triggered = 0
clarification_led_to_correction = 0
verifier_verdicts = {}
verifier_corrections = 0
corrections_by_type = {}
correction_details = []

for pid, trials in review.items():
    for tid, data in trials.items():
        if not isinstance(data, dict) or 'criteria' not in data:
            continue
        for c in data['criteria']:
            if 'criterion_type' not in c:
                continue
            total_criteria += 1

            a = c.get('assertion', {})
            all_sents = a.get('sentence_assertions', [])
            usable = a.get('usable_sentence_ids', [])
            assertion_total_sentences += len(all_sents)
            assertion_filtered += (len(all_sents) - len(usable))

            cl = c.get('clarification', {})
            triggered = cl.get('triggered', False)
            if triggered:
                clarification_triggered += 1

            v = c.get('verifier', {})
            verdict = v.get('verdict', 'N/A')
            if verdict != 'N/A':
                verifier_verdicts[verdict] = verifier_verdicts.get(verdict, 0) + 1

            initial = c.get('initial_eligibility')
            final = c.get('final_eligibility')
            if initial != final and initial is not None and final is not None:
                verifier_corrections += 1
                key = initial + " -> " + final
                corrections_by_type[key] = corrections_by_type.get(key, 0) + 1
                if triggered:
                    clarification_led_to_correction += 1

print("TOTAL CRITERIA REVIEWED:", total_criteria)
print()
print("=" * 60)
print("ASSERTION AGENT")
print("=" * 60)
print("  Sentences analyzed:", assertion_total_sentences)
print("  Sentences filtered (unusable):", assertion_filtered)
print("  Sentences kept (usable):", assertion_total_sentences - assertion_filtered)
if assertion_total_sentences > 0:
    print("  Filter rate: %d/%d = %.1f%%" % (assertion_filtered, assertion_total_sentences, assertion_filtered/assertion_total_sentences*100))
print()
print("=" * 60)
print("CLARIFICATION AGENT")
print("=" * 60)
print("  Times triggered: %d / %d criteria (%.1f%%)" % (clarification_triggered, total_criteria, clarification_triggered/total_criteria*100))
print("  Of those, led to a correction:", clarification_led_to_correction)
print("  NOT triggered:", total_criteria - clarification_triggered)
print()
print("=" * 60)
print("VERIFIER AGENT")
print("=" * 60)
print("  Total verdicts:", sum(verifier_verdicts.values()))
for v_name in sorted(verifier_verdicts.keys(), key=lambda x: -verifier_verdicts[x]):
    count = verifier_verdicts[v_name]
    print("    %-15s: %3d (%.1f%%)" % (v_name, count, count/total_criteria*100))
print("  Total corrections made:", verifier_corrections)
print()
print("  CORRECTION BREAKDOWN:")
for k in sorted(corrections_by_type.keys(), key=lambda x: -corrections_by_type[x]):
    print("    %s: %d" % (k, corrections_by_type[k]))
