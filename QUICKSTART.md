# Agentic-TrailGPT - Quick Start Guide

## ✅ Setup Complete

Your Agentic-TrailGPT environment is fully configured and tested with Groq API.

### Current Configuration
- **LLM Provider**: Groq (Free Tier)
- **Model**: `qwen/qwen3.8-27b`
- **API Key**: ✓ Configured in `.env`
- **Environment**: Virtual Python environment at `.venv/`
- **Status**: ✓ All tests passed

---

## 🚀 Running the Pipeline

### Option 1: Automated Pipeline (Recommended)
```bash
cd c:\Users\udayr\Downloads\llm project_trailgpt\Agentic-TrailGPT
.\.venv\Scripts\Activate.ps1
python run_pipeline.py
```

This runs all 4 stages in sequence:
1. Baseline Matching (cached retrieval)
2. Enhanced Matching (Assertion + Clarification + Verifier agents)
3. Aggregation (trial-level scoring)
4. Final Ranking

### Option 2: Manual Step-by-Step

**Activate environment first:**
```bash
.\.venv\Scripts\Activate.ps1
```

**Step 1: Download trial metadata** (one-time only)
```bash
curl -L -o dataset/trial_info.json https://ftp.ncbi.nlm.nih.gov/pub/lu/TrialGPT/trial_info.json
```

**Step 2: Run baseline matching**
```bash
python3 trialgpt_matching/run_matching.py sigir qwen/qwen3.8-27b
```

**Step 3: Run three LLM agents**
```bash
python3 trialgpt_agents/run_enhanced_matching.py sigir qwen/qwen3.8-27b "results/matching_results_sigir_qwen/qwen3.8-27b.json"
```

**Step 4: Run aggregation**
```bash
python3 trialgpt_ranking/run_aggregation.py sigir qwen/qwen3.8-27b "results/matching_results_sigir_qwen/qwen3.8-27b_enhanced.json"
```

**Step 5: Run final ranking**
```bash
python3 trialgpt_ranking/rank_results.py "results/matching_results_sigir_qwen/qwen3.8-27b_enhanced.json" "results/aggregation_results_sigir_qwen/qwen3.8-27b.json"
```

---

## 📊 Output Files

After running the pipeline, you'll find:

| File | Description |
|------|-------------|
| `matching_results_sigir_qwen/qwen3.8-27b.json` | Initial criterion-level matching |
| `matching_results_sigir_qwen/qwen3.8-27b_enhanced.json` | After all three agents |
| `matching_results_sigir_qwen/qwen3.8-27b_enhanced_review.json` | Cases flagged for human review |
| `aggregation_results_sigir_qwen/qwen3.8-27b.json` | Trial-level aggregated scores |

---

## 🧠 The Three Innovations

### 1. **Assertion Agent** 
Filters evidence by:
- **Subject**: Patient vs. Family vs. Other
- **Polarity**: Affirmed vs. Negated  
- **Temporality**: Current vs. Historical vs. Future

*Eliminates false positives from family history*

### 2. **Clarification Agent**
When initial matching returns "not enough information":
- Names the missing fact
- Searches the patient note again
- Returns new evidence to Assertion Agent

*Reduces premature "not enough info" errors (30.7% of baseline errors)*

### 3. **Verifier Agent**
Double-checks each criterion decision:
- **Verified**: Label matches evidence ✓
- **Corrected**: Label changed to match evidence
- **Uncertain**: Flagged for human review

*Catches label-evidence mismatches (26.9% of baseline errors)*

---

## 📈 Expected Improvements

| Metric | Baseline | Target |
|--------|----------|--------|
| Criterion Accuracy | 87.3% | ~90%+ |
| Explanation Quality | 87.8% | ~92%+ |
| Family History Errors | Unknown | Reduced |
| Label Ambiguity Errors | 26.9% | <20% |

---

## 🐛 Troubleshooting

### Issue: "GROQ_API_KEY not set"
**Fix**: Verify `.env` contains:
```
GROQ_API_KEY=your_groq_api_key_here
MODEL=qwen/qwen3.8-27b
```

### Issue: "Rate limited"
**Fix**: Groq free tier has 30 req/min limit. Wait a moment and retry.

### Issue: "Model not found"
**Fix**: Use `qwen/qwen3.8-27b` (confirmed working). Check available models:
```bash
python -c "from groq import Groq; client = Groq(); print([m.id for m in client.models.list().data])"
```

### Issue: "Module not found" errors
**Fix**: Activate virtual environment:
```bash
.\.venv\Scripts\Activate.ps1
```

---

## 📚 Project Structure

```
Agentic-TrailGPT/
├── .env                          # Configuration (API key, model)
├── run_pipeline.py              # Main pipeline runner ⭐
├── test_groq_connection.py      # Verify Groq setup
├── trialgpt_llm/
│   ├── client.py               # Groq LLM wrapper
│   └── __init__.py
├── trialgpt_assertion/          # Agent 1: Subject/Polarity/Temporality
│   └── TrialGPT.py
├── trialgpt_clarification/      # Agent 2: Evidence-gap re-search
│   └── TrialGPT.py
├── trialgpt_verifier/           # Agent 3: Entailment check
│   └── TrialGPT.py
├── trialgpt_matching/           # Baseline criterion matching
│   └── run_matching.py
├── trialgpt_ranking/            # Aggregation & ranking
│   ├── run_aggregation.py
│   └── rank_results.py
├── trialgpt_retrieval/          # Cached retrieval (no full MedCPT)
└── dataset/
    ├── sigir/                   # SIGIR 2016 benchmark
    ├── trec_2021/              # TREC 2021 benchmark
    └── trec_2022/              # TREC 2022 benchmark
```

---

## ✨ Key Features

✅ **Drop-in compatibility** - Works with official TrialGPT JSON format  
✅ **Evidence-usability filtering** - Avoids family history hallucinations  
✅ **Closed-loop re-search** - Finds missed evidence  
✅ **Independent verification** - Double-checks and corrects labels  
✅ **Human review flagging** - Uncertain cases marked for review  

---

## 📖 References

- **TrialGPT Paper**: Jin et al., Nature Communications 2024
- **Official TrialGPT**: https://github.com/epfl-dlab/TrialGPT
- **Groq API Docs**: https://groq.com/
- **SIGIR/TREC Benchmarks**: Used for evaluation

---

## 💡 Next Steps

1. **Run the pipeline**:
   ```bash
   .\.venv\Scripts\Activate.ps1
   python run_pipeline.py
   ```

2. **Review the results**:
   - Check accuracy improvements
   - Examine flagged cases for human review
   - Compare baseline vs. enhanced matching

3. **Analyze errors**:
   - How many family history errors were eliminated?
   - What proportion of "not enough info" cases were resolved?
   - Did label ambiguity improve?

4. **Publish findings**:
   - Document improvements per error category
   - Report cost/performance trade-offs
   - Compare to baseline TrialGPT

---

**Ready to run? Execute:**
```bash
.\.venv\Scripts\Activate.ps1
python run_pipeline.py
```
