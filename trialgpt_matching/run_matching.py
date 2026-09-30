__author__ = "qiao"

"""
Running the TrialGPT matching for three cohorts (sigir, TREC 2021, TREC 2022).
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

from TrialGPT import trialgpt_matching

if __name__ == "__main__":
	corpus = sys.argv[1]
	model = sys.argv[2]
	model_safe = model.replace("/", "_")
	patient_limit = int(os.getenv("PATIENT_LIMIT", "0"))
	patient_ids_env = os.getenv("PATIENT_IDS", "")
	allowed_patient_ids = set(patient_ids_env.split(",")) if patient_ids_env else None

	dataset = json.load(open(f"dataset/{corpus}/retrieved_trials.json"))

	output_path = f"results/matching_results_{corpus}_{model_safe}.json"

	if os.path.exists(output_path):
		output = json.load(open(output_path))
	else:
		output = {}

	processed_count = 0
	for instance in dataset:
		patient_id = instance["patient_id"]
		if allowed_patient_ids and patient_id not in allowed_patient_ids:
			continue
		patient = instance["patient"]
		sents = sent_tokenize(patient)
		sents.append("The patient will provide informed consent, and will comply with the trial protocol without any practical issues.")
		sents = [f"{idx}. {sent}" for idx, sent in enumerate(sents)]
		patient = "\n".join(sents)

		if patient_id not in output:
			output[patient_id] = {"0": {}, "1": {}, "2": {}}

		patient_had_work = False
		for label in ["2", "1", "0"]:
			if label not in instance:
				continue

			for trial in instance[label]:
				trial_id = trial["NCTID"]

				if trial_id in output[patient_id][label]:
					continue

				try:
					results = trialgpt_matching(trial, patient, model)
					output[patient_id][label][trial_id] = results
					patient_had_work = True

					with open(output_path, "w") as f:
						json.dump(output, f, indent=4)

					print(f"  {patient_id} / {trial_id} / label={label} done", flush=True)

				except Exception as e:
					print(f"  {patient_id} / {trial_id} error: {e}", flush=True)
					continue

		# Count this patient as processed if we did any work or it was already cached
		total_cached = sum(len(output[patient_id].get(l, {})) for l in ["0","1","2"])
		if total_cached > 0:
			processed_count += 1

		if patient_limit > 0 and processed_count >= patient_limit:
			print(f"\nReached patient limit ({patient_limit}). Stopping.", flush=True)
			break

	print(f"\nMatching complete. Processed {processed_count} patients.", flush=True)
	print(f"Output: {output_path}", flush=True)
