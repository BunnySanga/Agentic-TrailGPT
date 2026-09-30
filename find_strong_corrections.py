import json

review = json.load(open('results/matching_results_sigir_qwen_qwen3.8-27b_enhanced_review.json'))

corrections = []

for pid, trials in review.items():
    for tid, data in trials.items():
        if not isinstance(data, dict) or 'criteria' not in data:
            continue
        for c in data['criteria']:
            if 'criterion_type' not in c:
                continue
            initial = c.get('initial_eligibility')
            final = c.get('final_eligibility')
            if initial == final or initial is None or final is None:
                continue

            v = c.get('verifier', {})
            cl = c.get('clarification', {})
            verdict = v.get('verdict', 'N/A')
            support = v.get('support_level', 'N/A')
            issues = v.get('issues', [])
            criterion = c.get('criterion', '')
            ctype = c.get('criterion_type', '')

            # Classify: is this a "absence = not excluded" overcorrection or a real fix?
            is_absence_pattern = (
                initial == 'not excluded' and
                final == 'not enough information' and
                any('absence' in i.lower() or 'lack of mention' in i.lower() or
                    'does not mention' in i.lower() or 'not mentioned' in i.lower() or
                    'does not explicitly' in i.lower() or 'absence of' in i.lower() or
                    'does not provide' in i.lower() or 'not explicitly' in i.lower()
                    for i in issues)
            )

            corrections.append({
                'patient': pid,
                'trial': tid,
                'type': ctype,
                'criterion': criterion[:80],
                'before': initial,
                'after': final,
                'verdict': verdict,
                'support': support,
                'issues': issues,
                'clarification_triggered': cl.get('triggered', False),
                'is_absence_pattern': is_absence_pattern,
            })

print("=" * 70)
print("ALL 26 CORRECTIONS — CLASSIFIED")
print("=" * 70)

strong = [c for c in corrections if not c['is_absence_pattern']]
weak = [c for c in corrections if c['is_absence_pattern']]

print("\n>>> STRONG CORRECTIONS (not just absence-of-mention pattern):")
print("-" * 70)
for i, c in enumerate(strong, 1):
    print(f"\n  {i}. [{c['type']}] {c['criterion']}")
    print(f"     {c['before']} -> {c['after']}")
    print(f"     Verdict: {c['verdict']} | Support: {c['support']}")
    for issue in c['issues'][:2]:
        print(f"     Reason: {issue[:120]}")

print(f"\n\n>>> DEBATABLE CORRECTIONS (absence-of-mention pattern): {len(weak)}")
print("-" * 70)
for i, c in enumerate(weak, 1):
    print(f"\n  {i}. [{c['type']}] {c['criterion']}")
    print(f"     {c['before']} -> {c['after']}")
    print(f"     Reason: {c['issues'][0][:120] if c['issues'] else 'N/A'}")
