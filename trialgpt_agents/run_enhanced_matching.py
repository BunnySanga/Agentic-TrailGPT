"""Run the batched LLM post-matching agents over a TrialGPT results file.

Usage:
    python3 trialgpt_agents/run_enhanced_matching.py \
        sigir gpt-4-turbo results/matching_results_sigir_gpt-4-turbo.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    from nltk.tokenize import sent_tokenize
except ImportError:  # Keep the extension usable before the official requirements are installed.
    sent_tokenize = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trialgpt_agents.enhanced_matching import enhance_trial_matching


def _output_paths(matching_path: Path) -> tuple[Path, Path]:
    stem = matching_path.stem
    enhanced = matching_path.with_name(f"{stem}_enhanced.json")
    review = matching_path.with_name(f"{stem}_enhanced_review.json")
    return enhanced, review


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    with path.open() as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else default


def _save_outputs(enhanced_path: Path, review_path: Path, enhanced: dict, review: dict) -> None:
    with enhanced_path.open("w") as handle:
        json.dump(enhanced, handle, indent=2)
    with review_path.open("w") as handle:
        json.dump(review, handle, indent=2)


def _retrieved_trial_index(dataset: list[object]) -> tuple[dict[str, str], dict[tuple[str, str], dict]]:
    patients: dict[str, str] = {}
    trials: dict[tuple[str, str], dict] = {}
    for item in dataset:
        if not isinstance(item, dict):
            continue
        patient_id = item.get("patient_id")
        patient = item.get("patient")
        if not isinstance(patient_id, str) or not isinstance(patient, str):
            continue
        patients[patient_id] = patient
        for relevance_label in ("0", "1", "2"):
            for trial in item.get(relevance_label, []):
                if isinstance(trial, dict) and isinstance(trial.get("NCTID"), str):
                    trials[(patient_id, trial["NCTID"])] = trial
    return patients, trials


def _numbered_patient(patient: str) -> str:
    # The first matching stage appends this sentence, so later agents use the
    # exact same patient-note context and sentence IDs.
    if sent_tokenize is not None:
        sentences = sent_tokenize(patient)
    else:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", patient)
            if sentence.strip()
        ]
    sentences.append(
        "The patient will provide informed consent, and will comply with the trial protocol without any practical issues."
    )
    return "\n".join(f"{index}. {sentence}" for index, sentence in enumerate(sentences))


def main(argv: list[str]) -> int:
    if len(argv) not in (4, 5, 6):
        print(
            "Usage: python3 trialgpt_agents/run_enhanced_matching.py "
            "<corpus> <model> <matching_results.json> "
            "[enhanced_results.json] [review.json]"
        )
        return 2

    corpus = argv[1]
    model = argv[2]
    matching_path = Path(argv[3])
    default_enhanced, default_review = _output_paths(matching_path)
    enhanced_path = Path(argv[4]) if len(argv) >= 5 else default_enhanced
    review_path = Path(argv[5]) if len(argv) == 6 else default_review

    with matching_path.open() as handle:
        matching_results = json.load(handle)
    with (PROJECT_ROOT / "dataset" / corpus / "retrieved_trials.json").open() as handle:
        patients, trials = _retrieved_trial_index(json.load(handle))

    enhanced_results: dict[str, dict] = _load_json(enhanced_path, {})
    review_results: dict[str, dict] = _load_json(review_path, {})
    for patient_id, relevance_groups in matching_results.items():
        enhanced_results.setdefault(patient_id, {})
        review_results.setdefault(patient_id, {})
        patient = patients.get(patient_id)
        if patient is None or not isinstance(relevance_groups, dict):
            review_results[patient_id]["error"] = "Patient note or matching groups are missing."
            continue

        numbered_patient = _numbered_patient(patient)
        for relevance_label, trial_results in relevance_groups.items():
            enhanced_results[patient_id].setdefault(relevance_label, {})
            if not isinstance(trial_results, dict):
                continue
            for trial_id, matching_result in trial_results.items():
                if (
                    trial_id in enhanced_results[patient_id][relevance_label]
                    and isinstance(review_results[patient_id].get(trial_id), dict)
                    and review_results[patient_id][trial_id].get("agent_mode") == "llm_batched"
                ):
                    continue
                trial = trials.get((patient_id, trial_id))
                if trial is None:
                    enhanced_results[patient_id][relevance_label][trial_id] = matching_result
                    review_results[patient_id][trial_id] = {"error": "Retrieved trial was not found."}
                    _save_outputs(enhanced_path, review_path, enhanced_results, review_results)
                    continue
                try:
                    enhanced, review = enhance_trial_matching(
                        matching_result,
                        trial,
                        numbered_patient,
                        model=model,
                    )
                    enhanced_results[patient_id][relevance_label][trial_id] = enhanced
                    review_results[patient_id][trial_id] = review
                except Exception as error:
                    # Preserve the official result and continue with other trials.
                    enhanced_results[patient_id][relevance_label][trial_id] = matching_result
                    review_results[patient_id][trial_id] = {
                        "error": str(error),
                        "agent_mode": "llm_batched",
                    }
                _save_outputs(enhanced_path, review_path, enhanced_results, review_results)

    _save_outputs(enhanced_path, review_path, enhanced_results, review_results)
    print(f"Enhanced matching results: {enhanced_path}")
    print(f"Agent review sidecar: {review_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
