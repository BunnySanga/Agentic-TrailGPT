"""Shared Azure OpenAI JSON-call helpers for the LLM-powered extensions."""

from .client import call_json, get_groq_client

__all__ = ["call_json", "get_groq_client"]
