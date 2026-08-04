"""Small Azure OpenAI wrapper matching the official TrialGPT call pattern."""

from __future__ import annotations

import json
import os
import re
from typing import Any


def get_azure_client() -> Any:
    """Create the same Azure client used by the official TrialGPT modules."""
    from openai import AzureOpenAI

    return AzureOpenAI(
        api_version="2023-09-01-preview",
        azure_endpoint=os.getenv("OPENAI_ENDPOINT"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def call_json(
    system_prompt: str,
    user_prompt: str,
    model: str,
    *,
    client: Any | None = None,
) -> dict:
    """Call an Azure deployment and parse a JSON object from its response."""
    client = client or get_azure_client()
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


def parse_json_object(content: object) -> object:
    """Parse fenced JSON or JSON surrounded by a short model preamble."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response did not contain text")

    cleaned = content.strip()
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
