#!/usr/bin/env python3
"""Check every Groq key in GROQ_API_KEYS: valid, model available, rate limits.

Usage:
    python check_groq_keys.py

Keys are read from .env and only ever printed masked (last 4 characters).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = os.getenv("MODEL", "openai/gpt-oss-120b")


def load_keys() -> list[str]:
    raw = os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY") or ""
    keys = [key.strip() for key in raw.split(",") if key.strip()]
    return list(dict.fromkeys(keys))


def mask(key: str) -> str:
    return f"gsk_…{key[-4:]}"


def check_key(key: str) -> dict:
    client = Groq(api_key=key, max_retries=0)
    status = {"key": mask(key)}

    try:
        model_ids = {model.id for model in client.models.list().data}
    except Exception as error:
        status["ok"] = False
        status["error"] = _short_error(error)
        return status

    status["model_available"] = MODEL in model_ids
    if not status["model_available"]:
        status["ok"] = False
        status["error"] = f"model {MODEL} not available on this account"
        return status

    try:
        raw = client.chat.completions.with_raw_response.create(
            model=MODEL,
            messages=[{"role": "user", "content": 'Reply with {"ok": true}'}],
            temperature=0,
            max_tokens=16,
        )
        raw.parse()
    except Exception as error:
        status["ok"] = False
        status["error"] = _short_error(error)
        return status

    headers = raw.headers
    status["ok"] = True
    status["requests_per_day"] = headers.get("x-ratelimit-limit-requests")
    status["requests_left_today"] = headers.get("x-ratelimit-remaining-requests")
    status["tokens_per_minute"] = headers.get("x-ratelimit-limit-tokens")
    status["tokens_left_this_minute"] = headers.get("x-ratelimit-remaining-tokens")
    return status


def _short_error(error: Exception) -> str:
    text = str(error).replace("\n", " ")
    return text[:160]


def main() -> int:
    keys = load_keys()
    if not keys:
        print("No keys found. Set GROQ_API_KEYS (comma-separated) in .env.")
        return 1

    print(f"Model: {MODEL}")
    print(f"Reasoning effort: {os.getenv('GROQ_REASONING_EFFORT') or '(model default)'}")
    print(f"Workers: {os.getenv('MAX_WORKERS', '3')}")
    print(f"Keys:  {len(keys)} unique\n")

    working = 0
    for index, key in enumerate(keys, 1):
        status = check_key(key)
        if status["ok"]:
            working += 1
            print(
                f"[{index}] {status['key']}  OK   "
                f"req/day={status['requests_per_day']} (left {status['requests_left_today']})  "
                f"tokens/min={status['tokens_per_minute']}"
            )
        else:
            print(f"[{index}] {status['key']}  FAIL {status['error']}")

    print(f"\n{working}/{len(keys)} keys working")
    return 0 if working == len(keys) else 1


if __name__ == "__main__":
    sys.exit(main())
