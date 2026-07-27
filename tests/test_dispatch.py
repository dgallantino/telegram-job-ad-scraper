"""Tests for scraper URL validation and site-allowlist dispatch."""

from __future__ import annotations

import pytest

from job_scraper.scraper.dispatch import (
    get_fetch_user_agent,
    get_parser,
    is_supported_site,
    is_well_formed_url,
)
from job_scraper.scraper.sites import glints_site, jobstreet_site, threads_site


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://id.jobstreet.com/job/123", True),
        ("http://example.com/job", True),
        ("https://www.example.com", True),
        ("", False),
        ("not-a-url", False),
        ("ftp://example.com/file", False),
        ("/relative/path", False),
        ("https://", False),
        ("://missing-scheme.com", False),
    ],
)
def test_is_well_formed_url(url: str, expected: bool) -> None:
    assert is_well_formed_url(url) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://id.jobstreet.com/id/job/123", True),
        ("https://www.id.jobstreet.com/id/job/123", True),
        ("https://ID.JobStreet.com/job", True),
        ("https://glints.com/id/en/opportunities/jobs/abc", True),
        ("https://www.glints.com/id/en/opportunities/jobs/abc", True),
        ("https://example.com/ad", False),
        ("https://www.example.com/ad", False),
        ("https://www.threads.com/@user/post/Abc", True),
        ("https://threads.com/@user/post/Abc", True),
        ("https://www.threads.net/@user/post/Abc", True),
        ("https://threads.net/@user/post/Abc", True),
        ("https://jobs.example.org/ad", False),
        ("https://jobstreet.com/id/job/123", False),
        ("https://unsupported.example/job", False),
    ],
)
def test_is_supported_site(url: str, expected: bool) -> None:
    assert is_supported_site(url) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://id.jobstreet.com/job/1", jobstreet_site.parse),
        ("https://www.id.jobstreet.com/job/1", jobstreet_site.parse),
        ("https://glints.com/id/en/opportunities/jobs/abc", glints_site.parse),
        ("https://www.glints.com/id/en/opportunities/jobs/abc", glints_site.parse),
        ("https://EXAMPLE.com/job", None),
        ("https://www.threads.com/@user/post/Abc", threads_site.parse),
        ("https://threads.net/@user/post/Abc", threads_site.parse),
        ("https://unknown.example/job", None),
    ],
)
def test_get_parser(url: str, expected: object) -> None:
    assert get_parser(url) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://id.jobstreet.com/job/1", None),
        ("https://example.com/job", None),
        (
            "https://www.threads.com/@user/post/Abc",
            threads_site.FETCH_USER_AGENT,
        ),
        (
            "https://threads.net/@user/post/Abc",
            threads_site.FETCH_USER_AGENT,
        ),
    ],
)
def test_get_fetch_user_agent(url: str, expected: str | None) -> None:
    assert get_fetch_user_agent(url) is expected
