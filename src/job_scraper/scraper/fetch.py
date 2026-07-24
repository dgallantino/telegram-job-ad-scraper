"""Async HTML fetch for a single URL (no link-following)."""

from __future__ import annotations

import httpx

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def fetch_html(url: str, *, timeout: float = 30.0) -> str:
    """GET ``url`` and return the response body as text.

    Raises ``httpx.HTTPStatusError`` on non-2xx responses.
    """
    headers = {"User-Agent": _DEFAULT_USER_AGENT}
    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
