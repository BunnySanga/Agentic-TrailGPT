# Agentic-TrailGPT: LLM-Powered Clinical Trial Matching with Agent Post-Processing

## Project Overview

**Agentic-TrailGPT** extends the baseline TrialGPT system with three novel LLM-powered agents that refine criterion-level eligibility decisions. The system matches patients to clinical trials using a pipeline of:

1. **Retrieval**: Efficiently retrieve candidate trials from a large corpus
2. **Matching**: Per-criterion eligibility classification with explanations  
3. **Enhancement** (NEW): Post-matching agents for quality improvement
4. **Aggregation**: Combine criterion decisions into trial-level scores
5. **Ranking**: Rank trials by patient eligibility

This project addresses the primary failure modes identified in the TrialGPT Nature Communications paper (Jin et al., 2024) through targeted agent interventions.

---

## Three Core Innovations

### 1. **Assertion Agent** - Evidence Usability Filter
**Location**: `trialgpt_assertion/TrialGPT.py`

**Problem Addressed**: Subject confusion and negation errors (family history misattribution)
- TrialGPT may cite "Father has type 2 diabetes" as evidence for patient's diabetes
- Negated statements ("No chest pain") may be misinterpreted

**How It Works**:
Classifies every candidate evidence sentence along three dimensions:

```
subject (patient | family | other | unclear)
polarity (affirmed | negated | hypothetical | unclear)
temporality (current | historical | future/planned | unclear)
↓
Filters out unusable evidence (non-patient, hypothetical, negated diagnoses)
↓
Returns only usable patient evidence for next stages
```

**Key Rules**:
- Family history is NOT evidence that patient has condition
- Negated statements show absence, not presence → still usable
- Hypothetical/screening-only statements → not usable as confirmed facts
- Historical facts CAN be usable when relevant to criterion

**Example**:
```
Criterion: "Patient must NOT have diabetes."
Patient Note: 
  [1] Father has type 2 diabetes.
  [2] No history of diabetes mellitus in the patient.

Assertion Output:
  [1]: subject="family", usable=false → DROPPED
  [2]: subject="patient", polarity="negated", usable=true → KEPT
```

**Impact**: Reduces family-history hallucinations, improves precision on exclusion criteria

---

### 2. **Clarification Agent** - Evidence-Gap Re-Search
**Location**: `trialgpt_clarification/TrialGPT.py`

**Problem Addressed**: Premature "not enough information" (30.7% of baseline errors)
- Initial matching model gives up with "not enough info" even when evidence is present
- Example: Patient note says "Former smoker, quit 5 years ago" but model misses "non-smoker" inference

**How It Works**:
When triggered (initial label = "not enough information" OR Verifier flags gap):

```
1. Name the missing fact ("Is patient a non-smoker?")
2. Build targeted queries ("quit smoking", "smoke", "cessation", "former smoker")
3. Re-search THE SAME PATIENT NOTE (NOT new trials)
4. Pass newly found sentences through Assertion Agent
5. Return additional evidence if found
```

**Key Constraints**:
- Operates ONLY within current patient note
- Does not retrieve additional trials
- Does not invent facts
- Cannot make interactive requests

**Example**:
```
Initial Decision: "not enough information" (label missing "non-smoker" status)
Clarification Query: ["quit smoking", "former smoker", "smoking cessation"]
Found: [3] "Quit smoking 5 years ago"
After Assertion: [3] is affirmed patient statement → usable
Result: Evidence now available for re-evaluation
```

**Impact**: Recovers missing evidence in 30% of errors, enables correct classification

---

### 3. **Verifier Agent** - Entailment Check & Correction
**Location**: `trialgpt_verifier/TrialGPT.py`

**Problem Addressed**: Label ambiguity and unsupported decisions (26.9% of baseline errors)
- TrialGPT confuses "Not Excluded" vs "Not Enough Information"
- Explanations don't always match chosen label
- No dedicated verification module

**How It Works**:
After Matching + Assertion + Clarification:

```
Given: 
  - Criterion text
  - Proposed explanation
  - Proposed label
  - Evidence (patient sentences + Assertion annotations + Clarification results)

Output:
  - verdict (verified | unsupported | contradicted | uncertain)
  - support_level (strong | partial | weak | none)
  - corrected_eligibility (if unsupported/contradicted)
  - needs_human_review (if uncertain/weak)
```

**Correction Logic**:
- If label is unsupported by evidence → correct to "not enough information"
- If evidence contradicts label → correct to opposite valid label
- If support is weak but label is technically defensible → flag for review

**Valid Labels**:
- Inclusion: `included` | `not included` | `not enough information` | `not applicable`
- Exclusion: `excluded` | `not excluded` | `not enough information` | `not applicable`

**Example**:
```
Baseline Matching Output:
  criterion: "Patient must NOT have diabetes"
  explanation: "Patient has diabetes" (misquoted family history)
  label: "excluded"
  evidence: [1] "Father has type 2 diabetes"

After Assertion: [1] marked as family evidence (unusable)
Verifier Verdict: "contradicted" 
Corrected Label: "not excluded" (no patient diabetes found)
Needs Review: false
```

**Impact**: Reduces label noise, increases agreement with expert consensus

---

## End-to-End Pipeline

### Architecture Diagram
```
┌─────────────────┐
│ Patient Record  │
└────────┬────────┘
         │
    ┌────▼─────────────────────┐
    │  Cached Trial Retrieval   │  (TrialGPT baseline)
    │  (~90% recall, <6% corpus)│
    └────┬─────────────────────┘
         │
    ┌────▼─────────────────────┐
    │ Initial LLM Matching      │  (TrialGPT baseline)
    │ Per-criterion judgments   │
    └────┬─────────────────────┘
         │
    ┌────▼──────────────────────────────┐
    │ 1. ASSERTION AGENT                 │  (NEW - this project)
    │    ├─ Classify evidence: subject,  │
    │    │  polarity, temporality        │
    │    └─ Filter unusable evidence     │
    └────┬──────────────────────────────┘
         │
    ┌────▼──────────────────────────────┐
    │ 2. CLARIFICATION AGENT (if needed) │  (NEW - this project)
    │    ├─ Trigger: "not enough info"  │
    │    │           or Verifier gap     │
    │    ├─ Find missing facts           │
    │    ├─ Re-search patient note       │
    │    └─ Pass through Assertion       │
    └────┬──────────────────────────────┘
         │
    ┌────▼──────────────────────────────┐
    │ 3. VERIFIER AGENT                  │  (NEW - this project)
    │    ├─ Check support level          │
    │    ├─ Correct if needed            │
    │    └─ Flag uncertain cases         │
    └────┬──────────────────────────────┘
         │
    ┌────▼──────────────────────────────┐
    │ Aggregation                        │  (TrialGPT baseline)
    │ Combine criteria → trial-level     │
    └────┬──────────────────────────────┘
         │
    ┌────▼──────────────────────────────┐
    │ Ranking                            │  (TrialGPT baseline)
    │ Rank trials by eligibility         │
    └────▼──────────────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │ Output: Ranked Trials         │
    │ + Review Flags + Audit Trail  │
    └───────────────────────────────┘
```

---

## Project Structure

```
Agentic-TrailGPT/
├── claude.md                          # This file
├── README.md                          # Original TrialGPT documentation
├── requirements.txt                   # Python dependencies
│
├── dataset/                           # Public clinical trial datasets
│   ├── sigir/                         # SIGIR 2016 benchmark
│   │   ├── corpus.jsonl              # Trial descriptions
│   │   ├── queries.jsonl             # Patient summaries
│   │   ├── retrieved_trials.json     # Cached retrieval results
│   │   └── qrels/test.tsv            # Ground truth labels
│   ├── trec_2021/                    # TREC Clinical Trials 2021
│   └── trec_2022/                    # TREC Clinical Trials 2022
│
├── results/                           # Output files (generated)
│   ├── matching_results_*.json        # Baseline TrialGPT output
│   ├── matching_results_*_enhanced.json      # After Assertion/Clarification/Verifier
│   ├── matching_results_*_enhanced_review.json  # Agent audit trails
│   ├── aggregation_results_*.json    # Trial-level aggregation
│   └── final_ranking_*.json          # Ranked trial output
│
├── tests/                             # Unit tests
│   ├── test_enhanced_matching.py      # Tests for enhancement pipeline
│   └── test_llm_agents.py             # Agent unit tests
│
├── trialgpt_retrieval/                # Baseline retrieval stage
│   ├── keyword_generation.py
│   └── hybrid_fusion_retrieval.py
│
├── trialgpt_matching/                 # Baseline matching stage
│   └── run_matching.py
│
├── trialgpt_assertion/                # NEW: Assertion Agent
│   ├── __init__.py
│   └── TrialGPT.py                   # AssertionAgent class
│
├── trialgpt_clarification/            # NEW: Clarification Agent
│   ├── __init__.py
│   └── TrialGPT.py                   # ClarificationAgent class
│
├── trialgpt_verifier/                 # NEW: Verifier Agent
│   ├── __init__.py
│   └── TrialGPT.py                   # VerifierAgent class
│
├── trialgpt_agents/                   # NEW: Orchestration layer
│   ├── __init__.py
│   ├── contracts.py                  # Shared validation & utilities
│   ├── enhanced_matching.py          # Main orchestration logic
│   └── run_enhanced_matching.py      # CLI entry point
│
├── trialgpt_llm/                      # LLM API client
│   ├── __init__.py
│   └── client.py                     # Azure OpenAI wrapper
│
├── trialgpt_ranking/                  # Baseline aggregation & ranking
│   ├── rank_results.py
│   ├── run_aggregation.py
│   └── TrialGPT.py
│
└── LICENSE
```

---

## Setup & Configuration

### 1. Environment Setup

```bash
# Navigate to project root
cd /path/to/Agentic-TrailGPT

# Create virtual environment
python3 -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate
# OR activate (Windows)
.venv\Scripts\activate

# Install dependencies
python -m pip install -r requirements.txt
```

### 2. Azure OpenAI Credentials

Set these environment variables (recommended: add to `.env` or shell profile):

```bash
export OPENAI_ENDPOINT="https://YOUR-RESOURCE.openai.azure.com/"
export OPENAI_API_KEY="YOUR_API_KEY"
export MODEL="YOUR_AZURE_DEPLOYMENT_NAME"
```

Verify setup:
```bash
echo $OPENAI_ENDPOINT
echo $OPENAI_API_KEY
echo $MODEL
```

### 3. Download Trial Metadata

Required for aggregation stage:

```bash
curl -L -o dataset/trial_info.json \
  https://ftp.ncbi.nlm.nih.gov/pub/lu/TrialGPT/trial_info.json
```

### 4. (Optional) Download Additional Datasets

TREC datasets (large, ~10GB each):

```bash
# TREC 2021
curl -o dataset/trec_2021/corpus.jsonl \
  https://ftp.ncbi.nlm.nih.gov/pub/lu/TrialGPT/trec_2021_corpus.jsonl

# TREC 2022  
curl -o dataset/trec_2022/corpus.jsonl \
  https://ftp.ncbi.nlm.nih.gov/pub/lu/TrialGPT/trec_2022_corpus.jsonl
```

---

## Running the Pipeline

### Option A: Full End-to-End Pipeline (Recommended)

```bash
# 1. Baseline matching (cached retrieval)
python3 trialgpt_matching/run_matching.py sigir "$MODEL"

# 2. Enhancement: Run agents (Assertion → Clarification → Verifier)
python3 trialgpt_agents/run_enhanced_matching.py \
  sigir "$MODEL" \
  "results/matching_results_sigir_${MODEL}.json"

# 3. Aggregation (combine criteria into trial-level scores)
python3 trialgpt_ranking/run_aggregation.py \
  sigir "$MODEL" \
  "results/matching_results_sigir_${MODEL}_enhanced.json"

# 4. Final ranking (sort trials by eligibility)
python3 trialgpt_ranking/rank_results.py \
  "results/matching_results_sigir_${MODEL}_enhanced.json" \
  "results/aggregation_results_sigir_${MODEL}.json"
```

### Option B: Skip Enhancement (Baseline Only)

To run baseline TrialGPT without agents:

```bash
# 1. Baseline matching
python3 trialgpt_matching/run_matching.py sigir "$MODEL"

# 2. Aggregation with baseline results
python3 trialgpt_ranking/run_aggregation.py \
  sigir "$MODEL" \
  "results/matching_results_sigir_${MODEL}.json"

# 3. Ranking
python3 trialgpt_ranking/rank_results.py \
  "results/matching_results_sigir_${MODEL}.json" \
  "results/aggregation_results_sigir_${MODEL}.json"
```

### Option C: Just Enhancement (Skip Matching)

If baseline matching results already exist:

```bash
python3 trialgpt_agents/run_enhanced_matching.py \
  sigir "$MODEL" \
  "results/matching_results_sigir_${MODEL}.json"
```

---

## Output Files

After running the pipeline, inspect these key files:

### Baseline Matching
**File**: `results/matching_results_sigir_${MODEL}.json`

```json
{
  "patient_id": "1",
  "trial_id": "NCT123456",
  "criteria": [
    {
      "criterion_id": "0",
      "criterion": "Patient must have Stage III melanoma",
      "criterion_type": "inclusion",
      "explanation": "The patient was diagnosed with Stage III melanoma in 2023.",
      "relevant_sentence": [1],
      "eligibility": "included"
    }
  ]
}
```

### Enhanced Matching (After Agents)
**File**: `results/matching_results_sigir_${MODEL}_enhanced.json`

Same format as above, but eligibility labels may be corrected by agents.

### Enhancement Audit Trail
**File**: `results/matching_results_sigir_${MODEL}_enhanced_review.json`

Detailed trace of each agent's processing:

```json
{
  "patient_id": "1",
  "trial_id": "NCT123456",
  "criteria": [
    {
      "criterion_id": "0",
      "initial_eligibility": "excluded",
      "final_eligibility": "not excluded",
      "assertion": {
        "sentence_assertions": [
          {
            "id": 1,
            "subject": "family",
            "polarity": "affirmed",
            "temporality": "current",
            "usable_as_patient_evidence": false,
            "reason": "Family history is not patient evidence"
          }
        ]
      },
      "clarification": {
        "triggered": false,
        "trigger_reason": null
      },
      "verifier": {
        "verdict": "contradicted",
        "support_level": "none",
        "corrected_eligibility": "not excluded",
        "issues": ["Original evidence was family history, not patient fact"],
        "needs_human_review": false
      }
    }
  ]
}
```

### Aggregation Results
**File**: `results/aggregation_results_sigir_${MODEL}.json`

Trial-level scores combining all criteria.

---

## Running Tests

### Without Azure Credentials (Local Tests)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Expected output:
```
test_enhanced_matching (tests.test_enhanced_matching.TestEnhancedMatching) ... ok
test_llm_agents (tests.test_llm_agents.TestLLMAgents) ... ok
...
Ran X tests in Y.XXXs
OK
```

### With Azure Credentials (Integration Tests)

Same command (tests auto-detect credentials and run LLM-based tests):

```bash
python3 -m unittest discover -s tests -v
```

---

## Key Data Structures

### Patient Evidence Object
```python
{
  "id": 0,              # Sentence index
  "text": "..."         # Sentence text
}
```

### Assertion Output
```python
{
  "sentence_assertions": [
    {
      "id": 0,
      "text": "Father has type 2 diabetes",
      "subject": "family|patient|other|unclear",
      "polarity": "affirmed|negated|hypothetical|unclear",
      "temporality": "current|historical|future/planned|unclear",
      "usable_as_patient_evidence": true|false,
      "reason": "Family history is not patient evidence"
    }
  ]
}
```

### Clarification Output
```python
{
  "triggered": true|false,
  "trigger_reason": "initial_label_not_enough_information|verifier_gap|...",
  "missing_facts": [
    {
      "fact": "Is patient a non-smoker?",
      "why_needed": "Criterion requires non-smoker status",
      "queries": ["quit smoking", "former smoker", "smoking cessation"],
      "expected_evidence_type": "patient_historical_fact"
    }
  ],
  "candidate_sentence_ids": [3, 5, 7]
}
```

### Verifier Output
```python
{
  "verdict": "verified|unsupported|contradicted|uncertain",
  "support_level": "strong|partial|weak|none",
  "corrected_eligibility": "valid_label_or_null",
  "issues": ["Explanation conflicts with evidence", "..."],
  "needs_human_review": true|false
}
```

---

## Evaluation Metrics

The system is evaluated on:

### Criterion-Level Metrics
- **Accuracy**: % of correct labels vs. expert annotations (baseline: 87.3%)
- **Explanation Quality**: % rated "correct" by physicians (baseline: 87.8%)
- **Evidence Sentence Precision/Recall**: Baseline P=90.1%, R=87.9%

### Trial-Level Metrics
- **NDCG@10, P@10**: Ranking quality
- **AUROC**: Discrimination between eligible/ineligible trials
- **Correlation**: With human judgments

### Error Analysis
- **Category Tracking**: % reduction per error type (E1-E4)
  - E1: Incorrect reasoning (30.7% baseline)
  - E2: Medical knowledge gaps (15.4% baseline)
  - E3: Label ambiguity (26.9% baseline)
  - E4: Family history/negation errors (not quantified)

---

## Architecture Details

### Agent Orchestration (`trialgpt_agents/enhanced_matching.py`)

```python
def _batched_llm_enhancement(
    matching_result: dict,      # Baseline TrialGPT output
    trial: dict,                # Trial description
    patient_sentences: dict,    # Numbered patient note
    assertion_agent: AssertionAgent,
    clarification_agent: ClarificationAgent,
    verifier_agent: VerifierAgent,
) -> tuple[dict, dict]:         # Enhanced result + audit trail
    """
    For each criterion:
    1. Run Assertion on current evidence
    2. If triggered, run Clarification
    3. Run Verifier on final evidence + agents' outputs
    4. Correct label if needed
    5. Return enhanced result + review record
    """
```

### LLM Client Wrapper (`trialgpt_llm/client.py`)

Abstracts Azure OpenAI API calls:

```python
def call_json(
    system_prompt: str,
    user_prompt: str,
    model: str,
    client: Any | None = None,
) -> dict:
    """
    Call Azure OpenAI with structured prompt.
    Returns: Parsed JSON response from LLM
    """
```

### Validation (`trialgpt_agents/contracts.py`)

Utility functions for correctness:

```python
ALLOWED_LABELS = {
    "inclusion": {"included", "not included", "not enough information", "not applicable"},
    "exclusion": {"excluded", "not excluded", "not enough information", "not applicable"},
}

def is_valid_label(criterion_type: str, label: object) -> bool:
    """Ensure label is in TrialGPT's official label set"""
    
def numbered_patient_sentences(patient: str) -> dict[int, str]:
    """Parse patient note into {id: text} mapping"""
    
def coerce_sentence_ids(value: object) -> list[int]:
    """Normalize and validate sentence ID references"""
```

---

## Troubleshooting

### API Errors
```
Error: "Invalid Azure endpoint or API key"
→ Check OPENAI_ENDPOINT and OPENAI_API_KEY environment variables
→ Verify MODEL deployment exists in your Azure resource
```

### File Not Found
```
Error: "matching_results_sigir_${MODEL}.json not found"
→ Run baseline matching first: python3 trialgpt_matching/run_matching.py sigir "$MODEL"
```

### Out of Memory
```
Error: "CUDA out of memory" (if using GPU embeddings)
→ Reduce batch size in configs, or use CPU embeddings
→ Note: Current cached-retrieval pipeline doesn't use GPU
```

### Timeout in Enhancement Stage
```
Error: "Timeout calling LLM"
→ Network issue or LLM service under load
→ Check OPENAI_ENDPOINT is reachable
→ Retry with longer timeout
```

---

## References

### Core Papers
- **TrialGPT**: Jin, Q. et al. (2024). "Matching patients to clinical trials with large language models." *Nature Communications*, 15, 9074. https://doi.org/10.1038/s41467-024-53081-z

### Datasets
- **SIGIR 2016**: https://data.csiro.au/collection/csiro:17152
- **TREC 2021/2022**: https://www.trec-cds.org/
- **ClinicalTrials.gov**: https://clinicaltrials.gov/

### Related Work
- Chain-of-Thought prompting: Wei et al. (2022)
- Self-consistency: Wang et al. (2022)
- LLM verification: Cobbe et al. (2021), Chowdhury & Caragea (2024)
- Clinical NLP: Stoyanov et al. (2020) - family history extraction

---

## Project Status

**Current Phase**: Prototype implementation with agent post-processing

**Tested On**:
- SIGIR 2016 benchmark (183 patients, 1000+ criteria)
- Python 3.9+
- Azure OpenAI GPT-4 deployment

**Next Steps** (Future Work):
1. Evaluation on full TREC datasets
2. Ablation studies (each agent's individual contribution)
3. Fine-tuning on medical-specific LLMs
4. Integration with clinical trial databases
5. User interface for clinician review

---

## Contributing

When modifying agents:
1. Maintain TrialGPT label schema compatibility
2. Update `trialgpt_agents/contracts.py` validation
3. Add/update unit tests in `tests/`
4. Document changes in agent docstrings
5. Test with `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`

---

**Last Updated**: 2024-09-01
**Maintainers**: Agentic-TrailGPT Team
**License**: See LICENSE file
