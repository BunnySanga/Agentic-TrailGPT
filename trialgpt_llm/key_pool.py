"""Thread-safe pool of Groq API keys with per-key rate-limit cooldowns."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any

DEFAULT_MAX_WAIT_SECONDS = 900.0


class AllKeysExhausted(RuntimeError):
    """Every key is cooling down for longer than the pool is willing to wait."""


@dataclass
class KeySlot:
    name: str
    client: Any
    cooldown_until: float = 0.0
    in_flight: int = 0
    last_used: float = 0.0
    requests: int = 0
    rate_limited: int = 0
    rate_limit_streak: int = 0
    tokens: int = 0


class KeyPool:
    """Hand out the least-busy key; park rate-limited keys until they recover.

    Callers pair ``acquire()`` with ``release()``. When a call is rate limited
    the caller reports it with ``cooldown()`` before releasing, so no other
    thread picks that key until the provider's retry delay has passed.
    """

    def __init__(
        self,
        slots: list[KeySlot],
        *,
        max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS,
        clock=time.monotonic,
    ):
        if not slots:
            raise ValueError("KeyPool needs at least one key")
        self._slots = slots
        self._max_wait = max_wait_seconds
        self._clock = clock
        self._cond = threading.Condition()

    @property
    def slots(self) -> list[KeySlot]:
        return list(self._slots)

    def acquire(self) -> KeySlot:
        with self._cond:
            while True:
                now = self._clock()
                ready = [slot for slot in self._slots if slot.cooldown_until <= now]
                if ready:
                    slot = min(ready, key=lambda item: (item.in_flight, item.last_used))
                    slot.in_flight += 1
                    slot.last_used = now
                    slot.requests += 1
                    return slot

                wait = min(slot.cooldown_until for slot in self._slots) - now
                if wait > self._max_wait:
                    raise AllKeysExhausted(
                        f"All {len(self._slots)} keys are rate limited; the soonest "
                        f"recovers in {wait / 60:.0f} min. Re-run later to resume."
                    )
                self._cond.wait(timeout=wait)

    def release(self, slot: KeySlot) -> None:
        with self._cond:
            slot.in_flight -= 1
            self._cond.notify_all()

    def cooldown(self, slot: KeySlot, seconds: float) -> None:
        with self._cond:
            slot.cooldown_until = max(slot.cooldown_until, self._clock() + seconds)
            slot.rate_limited += 1
            slot.rate_limit_streak += 1

    def record_success(self, slot: KeySlot) -> None:
        with self._cond:
            slot.rate_limit_streak = 0

    def record_tokens(self, slot: KeySlot, tokens: int) -> None:
        with self._cond:
            slot.tokens += tokens

    def summary(self) -> list[dict]:
        with self._cond:
            return [
                {
                    "key": slot.name,
                    "requests": slot.requests,
                    "rate_limited": slot.rate_limited,
                    "tokens": slot.tokens,
                }
                for slot in self._slots
            ]


def load_api_keys() -> list[str]:
    raw = os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY") or ""
    keys = [key.strip() for key in raw.split(",") if key.strip()]
    return list(dict.fromkeys(keys))


def mask_key(key: str) -> str:
    return f"gsk_…{key[-4:]}"


_pool: KeyPool | None = None
_pool_lock = threading.Lock()


def get_key_pool() -> KeyPool:
    """Build the process-wide pool from GROQ_API_KEYS on first use."""
    global _pool
    with _pool_lock:
        if _pool is None:
            from groq import Groq

            keys = load_api_keys()
            if not keys:
                raise RuntimeError("No Groq keys found. Set GROQ_API_KEYS in .env.")
            # SDK retries are disabled so a 429 comes back to the pool, which
            # moves on to another key instead of blocking on this one.
            slots = [
                KeySlot(name=mask_key(key), client=Groq(api_key=key, max_retries=0))
                for key in keys
            ]
            max_wait = float(os.getenv("KEY_MAX_WAIT_SECONDS", DEFAULT_MAX_WAIT_SECONDS))
            _pool = KeyPool(slots, max_wait_seconds=max_wait)
        return _pool
