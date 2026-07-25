"""URL validation and site-allowlist dispatch.

Two independent checks happen before a URL is ever scraped:

1. Is it well-formed at all (``is_well_formed_url``)?
2. Is its host in our small, explicit allowlist of supported job sites
   (``is_supported_site`` / ``get_parser``)?

Only URLs that pass both are enqueued for scraping; everything else gets a
``rejected`` row in the ``jobs`` sheet (handled by callers, not here).
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

from job_scraper.scraper.sites import SITE_ALLOWLIST, ParserFunc



def is_well_formed_url(url: str) -> bool:
    """Return True if ``url`` is a syntactically valid absolute http(s) URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _normalize_host(url: str) -> str:
    host = urlparse(url).hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[len("www."):]
    return host


def is_supported_site(url: str) -> bool:
    """Return True if ``url``'s host is in the supported-site allowlist."""
    return _normalize_host(url) in SITE_ALLOWLIST


def get_parser(url: str) -> ParserFunc | None:
    """Look up the parser function registered for ``url``'s host, if any."""
    return SITE_ALLOWLIST.get(_normalize_host(url))
