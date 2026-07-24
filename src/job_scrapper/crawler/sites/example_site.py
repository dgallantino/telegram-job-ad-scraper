"""Placeholder parser for a hypothetical "example.com" job-ad site.

This is a stub demonstrating the expected parser function signature that
every real site module must implement: take the crawled URL plus its raw
HTML, and return a dict of Sheet A job fields. It performs no real parsing.

Real site modules should register themselves in
``job_scrapper.crawler.dispatch._SITE_ALLOWLIST`` once the actual list of
supported sites is decided.
"""

from __future__ import annotations


def parse(url: str, html: str) -> dict:
    """Parse a job-ad page into Sheet A job fields.

    Args:
        url: The exact URL that was crawled (no link-following).
        html: The raw HTML body fetched from ``url``.

    Returns:
        A dict with keys matching the Sheet A job-field columns:
        ``job_title``, ``job_description``, ``job_location``,
        ``job_company``, ``job_salary``, ``job_type``, ``job_posted_date``.

    TODO: Implement real parsing with BeautifulSoup once this site is
    confirmed as part of the supported allowlist.
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
