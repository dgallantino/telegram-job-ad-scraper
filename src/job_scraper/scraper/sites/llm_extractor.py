"""Lightweight sync LLM client for JSON-schema structured extraction.

Uses ``httpx`` only — no OpenAI / OpenRouter SDK. Callers supply the prompt
text and JSON schema; this module posts to OpenRouter's
``/v1/chat/completions`` endpoint with ``response_format`` and returns the
parsed object.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "openai/gpt-oss-20b:free"
_DEFAULT_TIMEOUT = 60.0

_FENCED_JSON_RE = re.compile(
    r"^```(?:json)?\s*\n(?P<body>.*?)\n```\s*$",
    re.DOTALL | re.IGNORECASE,
)


class LlmExtractorError(RuntimeError):
    """Raised when an LLM request or response cannot be used."""


def _extract_chat_content(payload: dict[str, Any]) -> str:
    """Return ``choices[0].message.content`` from a chat completions body."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmExtractorError("LLM response missing choices array")

    first = choices[0]
    if not isinstance(first, dict):
        raise LlmExtractorError("LLM response choice is not an object")

    message = first.get("message")
    if not isinstance(message, dict):
        raise LlmExtractorError("LLM response missing message object")

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content

    raise LlmExtractorError("LLM response contained no message content")


def _coerce_json_text(raw: str) -> str:
    """Normalize model output into a JSON string for ``json.loads``.

    Some models wrap a valid JSON object in a markdown code fence even when
    structured output was requested. Strip that wrapper when present.
    """
    text = raw.strip()
    match = _FENCED_JSON_RE.match(text)
    if match is not None:
        return match.group("body").strip()
    return text


def extract_with_json_schema(
    *,
    input_text: str,
    schema: dict[str, Any],
    schema_name: str = "extracted_fields",
    model: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call OpenRouter with a JSON Schema and return the parsed object.

    Env vars (read at call time):
      - ``OPENROUTER_API_KEY`` — required; if missing, returns ``{}``.
      - ``OPENROUTER_MODEL`` — default ``openai/gpt-oss-20b:free``.
      - ``OPENROUTER_BASE_URL`` — default
        ``https://openrouter.ai/api/v1/chat/completions``.

    Raises:
        LlmExtractorError: On HTTP / parse failures when a key is configured.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        logger.info("OPENROUTER_API_KEY not set; skipping LLM call")
        return {}

    resolved_model = (
        model or os.environ.get("OPENROUTER_MODEL", "").strip() or _DEFAULT_MODEL
    )
    base_url = (
        os.environ.get("OPENROUTER_BASE_URL", "").strip() or _DEFAULT_BASE_URL
    )

    body: dict[str, Any] = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": input_text}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
        # Prefer providers that actually enforce json_schema.
        "provider": {"require_parameters": True},
        # Soft-repair markdown fences / minor JSON defects from free models.
        "plugins": [{"id": "response-healing"}],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(base_url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise LlmExtractorError(f"LLM HTTP error: {exc}") from exc
    except ValueError as exc:
        raise LlmExtractorError(f"LLM returned non-JSON body: {exc}") from exc

    if not isinstance(payload, dict):
        raise LlmExtractorError("LLM response is not a JSON object")

    if payload.get("error"):
        raise LlmExtractorError(f"LLM API error: {payload['error']!r}")

    raw_text = _extract_chat_content(payload)
    json_text = _coerce_json_text(raw_text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise LlmExtractorError(
            f"LLM output_text is not valid JSON: {raw_text[:200]!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise LlmExtractorError(
            f"LLM JSON root must be an object, got {type(parsed).__name__}"
        )
    return parsed
