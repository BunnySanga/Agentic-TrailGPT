"""Shared helpers for the agents: TrialGPT labels, criterion numbering, batching."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Iterator

# Groq's free tier rejects any single request above 8000 tokens (input plus
# expected output). Trials with 20+ criteria exceed that when every criterion
# goes into one agent call, so agents get criteria in chunks. Each criterion is
# judged independently, so chunking does not change what is asked about it.
AGENT_BATCH_CRITERIA = int(os.getenv("AGENT_BATCH_CRITERIA", "10"))
AGENT_BATCH_CHARS = int(os.getenv("AGENT_BATCH_CHARS", "12000"))


ALLOWED_LABELS = {
    "inclusion": {
        "included",
        "not included",
        "not enough information",
        "not applicable",
    },
    "exclusion": {
        "excluded",
        "not excluded",
        "not enough information",
        "not applicable",
    },
}


def fallback_label(criterion_type: str) -> str:
    """Return the conservative valid label for a criterion type."""
    if criterion_type not in ALLOWED_LABELS:
        raise ValueError(f"Unsupported criterion type: {criterion_type}")
    return "not enough information"


def is_valid_label(criterion_type: str, label: object) -> bool:
    """Check that a label remains compatible with TrialGPT's contract."""
    return isinstance(label, str) and label in ALLOWED_LABELS.get(criterion_type, set())


def numbered_patient_sentences(patient: str) -> dict[int, str]:
    """Parse TrialGPT's ``<id>. <sentence>`` patient-note representation."""
    sentences: dict[int, str] = {}
    for line in patient.splitlines():
        match = re.match(r"^\s*(\d+)\.\s*(.+?)\s*$", line)
        if match:
            sentences[int(match.group(1))] = match.group(2)
    return sentences


def coerce_sentence_ids(value: object) -> list[int]:
    """Return unique, non-negative integer sentence IDs in their input order."""
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []

    result: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            sentence_id = int(item)
        except (TypeError, ValueError):
            continue
        if sentence_id >= 0 and sentence_id not in result:
            result.append(sentence_id)
    return result



def criteria_by_id(criteria: object) -> dict[str, str]:
    """Mirror TrialGPT's criterion numbering without importing its API client."""
    if not isinstance(criteria, str):
        return {}

    parsed: dict[str, str] = {}
    index = 0
    for criterion in criteria.split("\n\n"):
        criterion = criterion.strip()
        if "inclusion criteria" in criterion.lower() or "exclusion criteria" in criterion.lower():
            continue
        if len(criterion) < 5:
            continue
        parsed[str(index)] = criterion
        index += 1
    return parsed


def request_chunks(requests: list[dict]) -> Iterator[list[dict]]:
    """Split agent requests by criterion count and serialized size."""
    chunk: list[dict] = []
    size = 0
    for request in requests:
        length = len(json.dumps(request, ensure_ascii=True))
        if chunk and (len(chunk) >= AGENT_BATCH_CRITERIA or size + length > AGENT_BATCH_CHARS):
            yield chunk
            chunk, size = [], 0
        chunk.append(request)
        size += length
    if chunk:
        yield chunk
