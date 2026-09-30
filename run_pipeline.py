#!/usr/bin/env python3
"""
Agentic-TrailGPT Pipeline Runner
Runs the complete pipeline: Matching -> Enhancement (3 Agents) -> Aggregation -> Ranking
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from dotenv import load_dotenv

os.environ["PYTHONUNBUFFERED"] = "1"
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("MODEL", "qwen/qwen3.8-27b")
MODEL_SAFE = MODEL.replace("/", "_")
DATASET = "sigir"

# How many patients to process (set low for free tier)
PATIENT_LIMIT = int(os.getenv("PATIENT_LIMIT", "3"))

print("=" * 70)
print("AGENTIC-TRAILGPT PIPELINE RUNNER")
print("=" * 70)
print(f"\n  Model: {MODEL}")
print(f"  Dataset: {DATASET}")
print(f"  Patient limit: {PATIENT_LIMIT}")
print(f"  API Key: {GROQ_API_KEY[:20]}...")

# Check trial metadata
trial_metadata_path = Path("dataset/trial_info.json")
if not trial_metadata_path.exists():
    print(f"\n  Trial metadata not found at {trial_metadata_path}")
    print("  Downloading...")
    os.system(
        "curl -L -o dataset/trial_info.json "
        "https://ftp.ncbi.nlm.nih.gov/pub/lu/TrialGPT/trial_info.json"
    )

# Ensure results directory
Path("results").mkdir(exist_ok=True)

# Define paths
matching_path = f"results/matching_results_{DATASET}_{MODEL_SAFE}.json"
enhanced_path = f"results/matching_results_{DATASET}_{MODEL_SAFE}_enhanced.json"
review_path = f"results/matching_results_{DATASET}_{MODEL_SAFE}_enhanced_review.json"
aggregation_base_path = f"results/aggregation_results_{DATASET}_{MODEL_SAFE}_baseline.json"
aggregation_enh_path = f"results/aggregation_results_{DATASET}_{MODEL_SAFE}.json"

# Define pipeline steps
steps = [
    {
        "name": "1. Baseline Matching",
        "cmd": f"python trialgpt_matching/run_matching.py {DATASET} {MODEL}",
        "output": matching_path,
        "description": "Per-criterion eligibility classification using LLM",
    },
    {
        "name": "2. Agent Enhancement (Assertion + Clarification + Verifier)",
        "cmd": f"python trialgpt_agents/run_enhanced_matching.py {DATASET} {MODEL} {matching_path}",
        "output": enhanced_path,
        "description": "Post-processing with 3 novel agents to fix errors",
    },
    {
        "name": "3. Aggregation (Trial-level scoring)",
        "cmd": f"python trialgpt_ranking/run_aggregation.py {DATASET} {MODEL} {enhanced_path}",
        "output": aggregation_enh_path,
        "description": "Combine criterion decisions into trial-level scores",
    },
    {
        "name": "4. Final Ranking & Comparison",
        "cmd": f"python compare_results.py {matching_path} {enhanced_path} {review_path}",
        "output": f"results/comparison_{DATASET}_{MODEL_SAFE}.json",
        "description": "Compare baseline vs enhanced results and show improvements",
    },
]

# Run pipeline
print("\n" + "=" * 70)
print("STARTING PIPELINE")
print("=" * 70)

failed = False
for i, step in enumerate(steps, 1):
    print(f"\n{'='*70}")
    print(f"[STEP {step['name']}]")
    print(f"  {step['description']}")
    print(f"  Command: {step['cmd']}")
    print("-" * 70)

    result = subprocess.run(step["cmd"], shell=True, cwd=Path.cwd())

    if result.returncode != 0:
        print(f"\n  STEP {i} FAILED (exit code {result.returncode})")
        failed = True
        break
    else:
        print(f"\n  Step {i} completed")
        if Path(step["output"]).exists():
            size_kb = Path(step["output"]).stat().st_size / 1024
            print(f"  Output: {step['output']} ({size_kb:.1f} KB)")

# Summary
print("\n" + "=" * 70)
if failed:
    print("PIPELINE EXECUTION FAILED")
    print("Note: Results are cached — re-run to resume from where it stopped.")
    sys.exit(1)
else:
    print("PIPELINE EXECUTION COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print("\nGenerated files:")
    results_dir = Path("results")
    if results_dir.exists():
        for file in sorted(results_dir.glob(f"*{MODEL_SAFE}*")):
            size_kb = file.stat().st_size / 1024
            print(f"  {file.name} ({size_kb:.1f} KB)")
    print("=" * 70)
