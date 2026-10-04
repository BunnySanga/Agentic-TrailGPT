__author__ = "qiao"

"""
Using GPT to aggregate the scores by itself.
"""

import json
from pathlib import Path
from nltk.tokenize import sent_tokenize
import os
import sys

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
for p in (_SCRIPT_DIR, _PROJECT_ROOT):
	if p not in sys.path:
		sys.path.insert(0, p)

from TrialGPT import trialgpt_aggregation

if __name__ == "__main__":
	corpus = sys.argv[1]
	model = sys.argv[2]
	model_safe = model.replace("/", "_")

	matching_results_path = sys.argv[3]
	results = json.load(open(matching_results_path))

	trial2info = json.load(open("dataset/trial_info.json"))

	# Load patient queries from queries.jsonl (no beir dependency needed)
	queries = {}
	with open(f"dataset/{corpus}/queries.jsonl") as f:
		for line in f:
			item = json.loads(line)
			queries[item["_id"]] = item["text"]

	# Optional 4th argument keeps baseline and enhanced aggregations in separate files.
	output_path = sys.argv[4] if len(sys.argv) > 4 else f"results/aggregation_results_{corpus}_{model_safe}.json"

	if os.path.exists(output_path):
		output = json.load(open(output_path))
	else:
		output = {}

	for patient_id, info in results.items():
		patient = queries[patient_id]
		sents = sent_tokenize(patient)
		sents.append("The patient will provide informed consent, and will comply with the trial protocol without any practical issues.")
		sents = [f"{idx}. {sent}" for idx, sent in enumerate(sents)]
		patient = "\n".join(sents)

		if patient_id not in output:
			output[patient_id] = {}

		for label, trials in info.items():
			for trial_id, trial_results in trials.items():
				if trial_id in output[patient_id]:
					continue

				if type(trial_results) is not dict:
					output[patient_id][trial_id] = "matching result error"

					with open(output_path, "w") as f:
						json.dump(output, f, indent=4)

					continue

				trial_info = trial2info[trial_id]

				try:
					result = trialgpt_aggregation(patient, trial_results, trial_info, model)
					output[patient_id][trial_id] = result

					with open(output_path, "w") as f:
						json.dump(output, f, indent=4)

				except Exception as e:
					print(f"Error aggregating {patient_id}/{trial_id}: {e}")
					continue
