"""Placeholder parser for a hypothetical "example.com" job-ad site.

This is a stub demonstrating the expected parser function signature that
every real site module must implement: take raw HTML and return
``JobFields``. It performs no real parsing.

Declare ``SITE_HOST`` and ``parse``; ``sites/__init__.py`` auto-registers
the module into ``SITE_ALLOWLIST``.
"""

from __future__ import annotations

from job_scraper.scraper.sites import JobFields

SITE_HOST = "example.com"


def parse(html: str) -> JobFields:
    """Parse a job-ad page into ``JobFields``.

    Args:
        html: The raw HTML body of the scraped page.
    """
    return JobFields(job_description="")
