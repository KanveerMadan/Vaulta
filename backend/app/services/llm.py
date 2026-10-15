"""
LLM calls (Groq, OpenAI-compatible chat completions with tool calling).

Everything sent to the model goes through `complete`, so tests replace this
one function to record the exact payloads.
"""

from __future__ import annotations

import httpx

from app.core.config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 20


class LLMError(Exception):
    """The model couldn't be reached or answered badly; callers reply gracefully."""


def complete(messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2) -> dict:
    """One chat completion. Returns the assistant message dict ({content, tool_calls?})."""
    if not settings.GROQ_API_KEY:
        raise LLMError("AI isn't configured on this server (GROQ_API_KEY).")
    body = {"model": settings.GROQ_MODEL, "messages": messages, "temperature": temperature}
    if tools:
        body.update(tools=tools, tool_choice="auto")
    try:
        res = httpx.post(GROQ_URL, json=body, timeout=REQUEST_TIMEOUT_SECONDS,
                         headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"})
        res.raise_for_status()
        return res.json()["choices"][0]["message"]
    except httpx.TimeoutException as e:
        raise LLMError("timeout") from e
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise LLMError(f"bad response: {e.__class__.__name__}") from e
