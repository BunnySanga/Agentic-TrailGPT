#!/usr/bin/env python3
"""Test Groq API connectivity."""

import os
import json
from dotenv import load_dotenv
from trialgpt_llm.client import call_json, get_groq_client

# Load environment variables
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("MODEL", "mixtral-8x7b-32768")

print("=" * 60)
print("GROQ API CONNECTIVITY TEST")
print("=" * 60)

# Check configuration
print(f"\n✓ API Key: {api_key[:20]}...")
print(f"✓ Model: {model}")

# Test 1: Groq client instantiation
print("\n[Test 1] Creating Groq client...")
try:
    client = get_groq_client()
    print("✓ Groq client created successfully")
except Exception as e:
    print(f"✗ Failed to create Groq client: {e}")
    exit(1)

# Test 2: Simple JSON response
print("\n[Test 2] Testing JSON parsing...")
try:
    result = call_json(
        system_prompt="You are a medical assistant. Return responses as JSON.",
        user_prompt='Return this as JSON: {"status": "ok", "message": "Groq is working"}',
        model=model,
        client=client
    )
    print(f"✓ JSON response: {json.dumps(result, indent=2)}")
except Exception as e:
    print(f"✗ Failed to parse JSON: {e}")
    exit(1)

# Test 3: Medical reasoning test
print("\n[Test 3] Testing medical reasoning...")
try:
    result = call_json(
        system_prompt="You are a medical expert analyzing patient eligibility. Return JSON with 'eligible' (true/false) and 'reason' keys.",
        user_prompt='Criterion: "Patient must not have diabetes." Patient: "No diabetes listed, Father has type 2." Is patient eligible?',
        model=model,
        client=client
    )
    print(f"✓ Medical reasoning: {json.dumps(result, indent=2)}")
except Exception as e:
    print(f"✗ Failed medical reasoning: {e}")
    exit(1)

print("\n" + "=" * 60)
print("✓ ALL TESTS PASSED - Groq is ready!")
print("=" * 60)
print("\nNext: Run the full pipeline")
print("  python3 trialgpt_matching/run_matching.py sigir mixtral-8x7b-32768")
