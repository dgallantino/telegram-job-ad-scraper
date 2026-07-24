"""Placeholder parser for a hypothetical "example.com" job-ad site.

This is a stub demonstrating the expected parser function signature that
every real site module must implement: take raw HTML and return a dict of
``jobs`` sheet job fields. It performs no real parsing.

Declare ``SITE_HOST`` and ``parse``; ``sites/__init__.py`` auto-registers
the module into ``SITE_ALLOWLIST``.
"""

from __future__ import annotations

SITE_HOST = "example.com"


def parse(html: str) -> dict:
    """Parse a job-ad page into ``jobs`` sheet job fields.

    Args:
        html: The raw HTML body of the scraped page.

    Returns:
        A dict with keys matching the ``jobs`` sheet job-field columns:
        ``job_title``, ``job_description``, ``job_location``,
        ``job_company``, ``job_salary``, ``job_type``, ``job_posted_date``.
    """
    return {
        "job_title": None,
        "job_description": None,
        "job_location": None,
        "job_company": None,
        "job_salary": None,
        "job_type": None,
        "job_posted_date": None,
    }
