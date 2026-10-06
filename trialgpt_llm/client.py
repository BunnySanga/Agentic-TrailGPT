"""Groq LLM wrapper for TrialGPT agent pipeline with multi-key rate-limit handling."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from dotenv import load_dotenv

from .key_pool import KeyPool, KeySlot, get_key_pool

load_dotenv()

MAX_RETRIES = 5
BASE_DELAY = 15
MAX_BACKOFF = 120

_usage_context = threading.local()


@contextmanager
def track_usage() -> Iterator[dict]:
    """Collect token usage of every call this thread makes inside the block.

    Retries after an invalid JSON reply are included, since they cost tokens.
    Requests rejected by a rate limit use no tokens and are not counted.
    """
    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "seconds": 0.0}
    previous = getattr(_usage_context, "usage", None)
    _usage_context.usage = usage
    try:
        yield usage
    finally:
        _usage_context.usage = previous


def _record_usage(prompt_tokens: int, completion_tokens: int, total_tokens: int, seconds: float) -> None:
    usage = getattr(_usage_context, "usage", None)
    if usage is None:
        return
    usage["calls"] += 1
    usage["prompt_tokens"] += prompt_tokens
    usage["completion_tokens"] += completion_tokens
    usage["total_tokens"] += total_tokens
    usage["seconds"] = round(usage["seconds"] + seconds, 2)


def call_json(
    system_prompt: str,
    user_prompt: str,
    model: str,
    *,
    client: Any | None = None,
) -> dict:
    """Call Groq and parse a JSON object from the response.

    Without ``client`` the call goes through the shared key pool built from
    GROQ_API_KEYS: a rate-limited key is parked for the provider's retry delay
    and the request moves to another key. Passing ``client`` uses only that
    client, with the same retry rules.
    """
    pool = get_key_pool() if client is None else KeyPool([KeySlot(name="client", client=client)])

    json_failures = 0
    transient_failures = 0
    while True:
        slot = pool.acquire()
        try:
            started = time.monotonic()
            content, (prompt_tokens, completion_tokens, total_tokens) = _complete(
                slot.client, system_prompt, user_prompt, model
            )
            pool.record_tokens(slot, total_tokens)
            _record_usage(prompt_tokens, completion_tokens, total_tokens, time.monotonic() - started)
        except Exception as error:
            if _is_request_too_large(error):
                raise
            if _is_rate_limit(error):
                delay = _retry_delay(error, slot.rate_limit_streak)
                pool.cooldown(slot, delay)
                print(f"  [{slot.name}] {_limit_kind(error)} hit, cooling {_format_seconds(delay)}", flush=True)
                continue
            if _is_transient(error) and transient_failures < MAX_RETRIES - 1:
                transient_failures += 1
                pool.cooldown(slot, 2 ** transient_failures)
                continue
            raise
        finally:
            pool.release(slot)

        try:
            result = parse_json_object(content)
            if not isinstance(result, dict):
                raise ValueError("LLM response must be a JSON object")
        except ValueError:
            json_failures += 1
            if json_failures >= MAX_RETRIES:
                raise
            print(f"  JSON parse failed (attempt {json_failures}/{MAX_RETRIES}), retrying...", flush=True)
            continue

        pool.record_success(slot)
        return result


def _complete(
    client: Any, system_prompt: str, user_prompt: str, model: str
) -> tuple[object, tuple[int, int, int]]:
    """Return the response text and (prompt, completion, total) tokens used."""
    kwargs: dict[str, Any] = {}
    reasoning_effort = os.getenv("GROQ_REASONING_EFFORT")
    if reasoning_effort:
        # gpt-oss models: "low" keeps hidden reasoning short, which roughly
        # halves output tokens against the daily token cap.
        kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        **kwargs,
    )
    usage = getattr(response, "usage", None)
    counts = tuple(
        getattr(usage, field, 0) or 0 for field in ("prompt_tokens", "completion_tokens", "total_tokens")
    )
    return response.choices[0].message.content, counts


def _limit_kind(error: Exception) -> str:
    """Name the limit Groq reports, e.g. 'tokens per day (TPD)'."""
    match = re.search(r"on ((?:input |output )?(?:requests|tokens) per (?:minute|day) \([A-Z]+\))", str(error))
    return match.group(1) if match else "rate limit"


def _status_code(error: Exception) -> int | None:
    status = getattr(error, "status_code", None)
    return status if isinstance(status, int) else None


def _is_rate_limit(error: Exception) -> bool:
    status = _status_code(error)
    if status is not None:
        return status == 429
    text = str(error).lower()
    return "429" in text or "rate_limit" in text or "rate limit" in text


def _is_request_too_large(error: Exception) -> bool:
    # A single request above the per-minute token limit can never succeed;
    # retrying it would loop forever.
    return _status_code(error) == 413 or "request too large" in str(error).lower()


def _is_transient(error: Exception) -> bool:
    status = _status_code(error)
    if status is not None:
        return status >= 500
    return type(error).__name__ in {"APIConnectionError", "APITimeoutError"}


def _retry_delay(error: Exception, streak: int) -> float:
    """Use the provider's retry delay when given, else exponential backoff."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or {}
    try:
        retry_after = float(headers.get("retry-after"))
        return retry_after + 1
    except (TypeError, ValueError):
        pass

    parsed = parse_retry_after(str(error))
    if parsed is not None:
        return parsed + 1
    return min(BASE_DELAY * (2 ** streak), MAX_BACKOFF)


def _format_seconds(seconds: float) -> str:
    return f"{seconds:.0f}s" if seconds < 120 else f"{seconds / 60:.0f} min"


def parse_retry_after(message: str) -> float | None:
    """Parse Groq's 'try again in 1m26.4s' style delay into seconds."""
    match = re.search(r"try again in\s+((?:\d+(?:\.\d+)?(?:ms|h|m|s))+)", message, re.IGNORECASE)
    if not match:
        return None
    scale = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
    return sum(
        float(value) * scale[unit.lower()]
        for value, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", match.group(1), re.IGNORECASE)
    )


def parse_json_object(content: object) -> object:
    """Parse fenced JSON or JSON surrounded by a short model preamble."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response did not contain text")

    cleaned = content.strip()

    # Strip <think>...</think> blocks that some reasoning models emit
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for start in (cleaned.find("{"), cleaned.find("[")):
            if start < 0:
                continue
            try:
                value, _ = decoder.raw_decode(cleaned[start:])
                return value
            except json.JSONDecodeError:
                continue
        raise ValueError("LLM response did not contain valid JSON")
