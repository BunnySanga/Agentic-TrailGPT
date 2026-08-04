"""Shared validation helpers for the post-matching agent pipeline."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


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


def patient_evidence(patient_sentences: Mapping[int, str], sentence_ids: object) -> list[dict]:
    """Build stable evidence objects for agent output and review sidecars."""
    return [
        {"id": sentence_id, "text": patient_sentences[sentence_id]}
        for sentence_id in coerce_sentence_ids(sentence_ids)
        if sentence_id in patient_sentences
    ]
