"""Tests for the generic sync LLM JSON-schema extractor."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from job_scraper.scraper.sites import llm_extractor
from job_scraper.scraper.sites.llm_extractor import (
    LlmExtractorError,
    _coerce_json_text,
    _extract_chat_content,
    extract_with_json_schema,
)


def test_extract_chat_content_from_choices() -> None:
    payload = {
        "choices": [
            {"message": {"role": "assistant", "content": '{"job_title": "Engineer"}'}}
        ]
    }
    assert _extract_chat_content(payload) == '{"job_title": "Engineer"}'


def test_extract_chat_content_missing_raises() -> None:
    with pytest.raises(LlmExtractorError, match="missing choices"):
        _extract_chat_content({"choices": []})


def test_extract_chat_content_empty_content_raises() -> None:
    with pytest.raises(LlmExtractorError, match="no message content"):
        _extract_chat_content({"choices": [{"message": {"content": "  "}}]})


def test_extract_with_json_schema_skips_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = extract_with_json_schema(
        input_text="unused",
        schema={"type": "object", "properties": {}},
    )
    assert result == {}


def test_extract_with_json_schema_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"job_title": "Analyst"}),
                }
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = mock_response

    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=mock_client))

    result = extract_with_json_schema(
        input_text="extract fields",
        schema={
            "type": "object",
            "properties": {"job_title": {"type": ["string", "null"]}},
            "required": [],
            "additionalProperties": False,
        },
    )
    assert result == {"job_title": "Analyst"}
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    sent_json: dict[str, Any] = call_kwargs.kwargs["json"]
    assert sent_json["model"] == "test/model"
    assert sent_json["messages"] == [
        {"role": "user", "content": "extract fields"}
    ]
    assert sent_json["response_format"]["type"] == "json_schema"
    assert sent_json["response_format"]["json_schema"]["strict"] is True
    assert sent_json["plugins"] == [{"id": "response-healing"}]
    assert "text" not in sent_json
    assert "input" not in sent_json


def test_coerce_json_text_strips_markdown_fence() -> None:
    fenced = '```json\n{\n  "job_type": "Contract"\n}\n```\n'
    assert json.loads(_coerce_json_text(fenced)) == {"job_type": "Contract"}
    assert _coerce_json_text('{"a": 1}') == '{"a": 1}'


def test_extract_with_json_schema_accepts_fenced_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '```json\n{"job_company": "Acme"}\n```\n',
                }
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = mock_response
    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=mock_client))

    result = extract_with_json_schema(
        input_text="x",
        schema={"type": "object", "properties": {}},
    )
    assert result == {"job_company": "Acme"}


def test_extract_with_json_schema_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.side_effect = httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=mock_client))

    with pytest.raises(LlmExtractorError, match="HTTP error"):
        extract_with_json_schema(
            input_text="x",
            schema={"type": "object", "properties": {}},
        )


def test_extract_with_json_schema_invalid_json_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": '["not", "an", "object"]'}}
        ]
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = mock_response
    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=mock_client))

    with pytest.raises(LlmExtractorError, match="must be an object"):
        extract_with_json_schema(
            input_text="x",
            schema={"type": "object", "properties": {}},
        )


def test_module_exports_error() -> None:
    assert issubclass(llm_extractor.LlmExtractorError, RuntimeError)
