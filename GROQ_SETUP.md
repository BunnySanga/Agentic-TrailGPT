# Groq API Integration Guide

## Overview
The Agentic-TrailGPT pipeline has been configured to use **Groq's free tier API** instead of Azure OpenAI. This guide explains the configuration and how to run the pipeline.

---

## Model Selection

### Recommended: **mixtral-8x7b-32768**
- **Speed**: Fast inference (ideal for real-time trial matching)
- **Quality**: Excellent reasoning and instruction-following
- **Context**: 32k token limit (sufficient for patient notes + trials)
- **Best for**: Complex medical criteria analysis and JSON output parsing

### Alternative Models (Groq Free Tier)
1. **llama2-70b-4096**
   - Larger model, potentially better reasoning
   - 4k token limit (may cause issues with long criteria)
   - Slower but more capable

2. **gemma-7b-it**
   - Instruction-tuned, smaller/faster
   - Good for simple criteria matching
   - Less reliable JSON parsing

**⚠️ Recommendation: Use `mixtral-8x7b-32768` for best performance**

---

## Configuration

### .env File
```bash
# Groq API Configuration (Free Tier)
GROQ_API_KEY=your_groq_api_key_here

# Model: mixtral-8x7b-32768 (recommended)
MODEL=mixtral-8x7b-32768
```

### Environment Variables
When running the pipeline, ensure these are exported:
```bash
export GROQ_API_KEY="your_api_key_here"
export MODEL="mixtral-8x7b-32768"
```

---

## Code Changes Made

### 1. `trialgpt_llm/client.py`
**Changed from**: Azure OpenAI client
**Changed to**: Groq client

```python
# OLD: from openai import AzureOpenAI
# NEW: from groq import Groq

def get_groq_client() -> Any:
    from groq import Groq
    return Groq(api_key=os.getenv("GROQ_API_KEY"))
```

The `call_json()` function remains the same, but now uses Groq's API instead.

### 2. `trialgpt_llm/__init__.py`
**Updated exports**:
```python
# OLD: get_azure_client
# NEW: get_groq_client
```

### 3. `requirements.txt`
**Added**:
```
groq==0.10.0
```

### 4. `.env`
**Updated from**: `API_KEY=...` (generic)
**Updated to**: `GROQ_API_KEY=...` (specific to Groq)

---

## Installation & Setup

### Step 1: Install Dependencies
```bash
cd c:\Users\udayr\Downloads\llm project_trailgpt\Agentic-TrailGPT
python -m pip install -r requirements.txt
```

### Step 2: Verify API Key
Ensure your .env file has:
```bash
GROQ_API_KEY=your_groq_api_key_here
MODEL=mixtral-8x7b-32768
```

### Step 3: Quick Test
```bash
python3 -c "
from trialgpt_llm.client import call_json
result = call_json(
    'You are a helpful assistant.',
    'What is 2+2?',
    'mixtral-8x7b-32768'
)
print(result)
"
```

---

## Running the Pipeline

### Full Pipeline
```bash
# 1. Download trial metadata
curl -L -o dataset/trial_info.json \
  https://ftp.ncbi.nlm.nih.gov/pub/lu/TrialGPT/trial_info.json

# 2. Run matching with cached retrieval
python3 trialgpt_matching/run_matching.py sigir mixtral-8x7b-32768

# 3. Run three LLM agents (Assertion, Clarification, Verifier)
python3 trialgpt_agents/run_enhanced_matching.py sigir mixtral-8x7b-32768 \
  "results/matching_results_sigir_mixtral-8x7b-32768.json"

# 4. Run aggregation
python3 trialgpt_ranking/run_aggregation.py sigir mixtral-8x7b-32768 \
  "results/matching_results_sigir_mixtral-8x7b-32768_enhanced.json"

# 5. Run final ranking
python3 trialgpt_ranking/rank_results.py \
  "results/matching_results_sigir_mixtral-8x7b-32768_enhanced.json" \
  "results/aggregation_results_sigir_mixtral-8x7b-32768.json"
```

### Run Tests Only
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

---

## Output Files

| File | Description |
|------|-------------|
| `matching_results_sigir_mixtral-8x7b-32768.json` | Initial criterion matching (no agents) |
| `matching_results_sigir_mixtral-8x7b-32768_enhanced.json` | After Assertion + Clarification + Verifier |
| `matching_results_sigir_mixtral-8x7b-32768_enhanced_review.json` | Cases flagged for human review |
| `aggregation_results_sigir_mixtral-8x7b-32768.json` | Trial-level aggregated scores |

---

## Three Agent Innovations

### 1. **Assertion Agent** (`trialgpt_assertion/TrialGPT.py`)
Filters evidence by:
- **Subject**: Patient vs. Family vs. Other
- **Polarity**: Affirmed vs. Negated vs. Hypothetical
- **Temporality**: Current vs. Historical vs. Future

Drops non-patient and hypothetical evidence.

### 2. **Clarification Agent** (`trialgpt_clarification/TrialGPT.py`)
When matching returns "not enough information":
1. Names the missing fact
2. Builds search queries
3. Re-searches the same patient note
4. Passes findings to Assertion Agent

### 3. **Verifier Agent** (`trialgpt_verifier/TrialGPT.py`)
Compares final evidence to proposed label:
- **Verified**: Label matches evidence ✓
- **Corrected**: Label changed to match evidence
- **Uncertain**: Flagged for human review

---

## Troubleshooting

### Issue: "GROQ_API_KEY not set"
**Solution**: Ensure .env file is in the repo root and contains:
```bash
GROQ_API_KEY=your_groq_api_key_here
```

### Issue: "Failed to parse JSON"
**Possible causes**:
1. Groq is returning text instead of JSON
2. Token limit exceeded
3. Model timeout

**Solution**: Try `llama2-70b-4096` or reduce input size

### Issue: "Rate limited"
**Cause**: Groq free tier has rate limits
**Solution**: Add delays between requests or upgrade to Groq paid tier

### Issue: "Model not found"
**Solution**: Check available models:
```bash
python3 -c "
from groq import Groq
client = Groq()
# Available models: mixtral-8x7b-32768, llama2-70b-4096, gemma-7b-it
"
```

---

## Groq API Limits (Free Tier)

| Metric | Limit |
|--------|-------|
| Requests per minute | 30 |
| Tokens per minute | 6,000 |
| Concurrent requests | 1 |
| Context window | 32k (mixtral), 4k (llama2) |

---

## Next Steps

1. ✅ Install dependencies: `pip install -r requirements.txt`
2. ✅ Verify .env configuration
3. ✅ Run tests: `python3 -m unittest discover -s tests -v`
4. ✅ Download trial metadata
5. ✅ Run the full pipeline

---

## References

- **Groq API Docs**: https://groq.com/
- **TrialGPT Paper**: Jin et al., Nature Communications 2024
- **Official TrialGPT GitHub**: https://github.com/epfl-dlab/TrialGPT
- **Agentic-TrailGPT**: Enhanced version with three new agents
