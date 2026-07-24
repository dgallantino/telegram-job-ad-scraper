"""Tests for async HTML fetch (mocked httpx; no network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from job_scraper.scraper.fetch import fetch_html


def _mock_client(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_fetch_html_returns_body_on_200() -> None:
    response = MagicMock()
    response.text = "<html>ok</html>"
    response.raise_for_status = MagicMock()

    with patch("job_scraper.scraper.fetch.httpx.AsyncClient", return_value=_mock_client(response)):
        body = await fetch_html("https://example.com/job")

    assert body == "<html>ok</html>"
    response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_html_raises_on_non_2xx() -> None:
    request = httpx.Request("GET", "https://example.com/missing")
    response = httpx.Response(404, request=request)

    with patch(
        "job_scraper.scraper.fetch.httpx.AsyncClient",
        return_value=_mock_client(response),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_html("https://example.com/missing")
