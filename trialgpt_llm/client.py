"""Groq LLM wrapper for TrialGPT agent pipeline with rate-limit retry."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from dotenv import load_dotenv

load_dotenv()

MAX_RETRIES = 5
BASE_DELAY = 15


def get_groq_client() -> Any:
    """Create a Groq client using the free tier API."""
    from groq import Groq

    return Groq(api_key=os.getenv("GROQ_API_KEY"))


def call_json(
    system_prompt: str,
    user_prompt: str,
    model: str,
    *,
    client: Any | None = None,
) -> dict:
    """Call Groq API and parse a JSON object from its response, with retry on rate limits."""
    client = client or get_groq_client()

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            content = response.choices[0].message.content
            result = parse_json_object(content)
            if not isinstance(result, dict):
                raise ValueError("LLM response must be a JSON object")
            return result

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                if "(TPD)" in error_str and "tokens per day" in error_str.lower():
                    raise RuntimeError("Daily token limit reached — skipping")
                # Per-minute or per-request limit: wait and retry
                wait_time = _extract_retry_delay(error_str, attempt)
                wait_time = min(wait_time, 30)
                print(f"  Rate limited (attempt {attempt+1}/{MAX_RETRIES}), waiting {wait_time:.0f}s...", flush=True)
                time.sleep(wait_time)
                continue
            if "JSON" in error_str and attempt < MAX_RETRIES - 1:
                print(f"  JSON parse failed (attempt {attempt+1}/{MAX_RETRIES}), retrying...", flush=True)
                time.sleep(2)
                continue
            raise

    raise RuntimeError(f"Failed after {MAX_RETRIES} retries")


def _extract_retry_delay(error_str: str, attempt: int) -> float:
    """Extract the suggested retry delay from the error message, or use exponential backoff."""
    match = re.search(r"try again in (\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
    if match:
        return float(match.group(1)) + 2

    match = re.search(r"try again in (\d+)m", error_str, re.IGNORECASE)
    if match:
        return float(match.group(1)) * 60 + 5

    return BASE_DELAY * (2 ** attempt)


def parse_json_object(content: object) -> object:
    """Parse fenced JSON or JSON surrounded by a short model preamble."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response did not contain text")

    cleaned = content.strip()

    # Strip <think>...</think> blocks (common with qwen models)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for start, marker in ((cleaned.find("{"), "{"), (cleaned.find("["), "[")):
            if start < 0:
                continue
            try:
                value, _ = decoder.raw_decode(cleaned[start:])
                return value
            except json.JSONDecodeError:
                continue
        raise ValueError("LLM response did not contain valid JSON")
