import json

review = json.load(open('results/matching_results_sigir_qwen_qwen3.8-27b_enhanced_review.json'))
enhanced = json.load(open('results/matching_results_sigir_qwen_qwen3.8-27b_enhanced.json'))

removed = 0
for pid in list(review.keys()):
    for tid in list(review[pid].keys()):
        data = review[pid][tid]
        if isinstance(data, dict) and ('error' in data or data.get('agent_mode') != 'llm_batched'):
            del review[pid][tid]
            for label in ['0', '1', '2']:
                if isinstance(enhanced.get(pid, {}).get(label), dict):
                    enhanced[pid][label].pop(tid, None)
            removed += 1

with open('results/matching_results_sigir_qwen_qwen3.8-27b_enhanced_review.json', 'w') as f:
    json.dump(review, f, indent=2)
with open('results/matching_results_sigir_qwen_qwen3.8-27b_enhanced.json', 'w') as f:
    json.dump(enhanced, f, indent=2)
print(f"Cleared {removed} errored entries")
