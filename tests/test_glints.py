"""Tests for glints.com job-detail HTML parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_scraper.scraper.sites.glints_site import parse
from job_scraper.scraper.sites.models import JobFields

_FIXTURES = Path(__file__).parent / "fixtures" / "glints"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_parse_full_fixture() -> None:
    result = parse(_load("detail_full.html"))
    assert result == JobFields(
        job_description="Build APIs.\nShip features.",
        job_title="Backend Engineer",
        job_location="Sleman, DI Yogyakarta",
        job_company="Acme Corp",
        job_salary="IDR 15000000 – 25000000 per month",
        job_type="Full time",
        job_posted_date="2026-07-01T08:00:00.000Z",
    )


def test_parse_no_salary() -> None:
    result = parse(_load("detail_no_salary.html"))
    assert result == JobFields(
        job_description="Ship integrations.",
        job_title="Contract Developer",
        job_location="Jakarta Selatan, DKI Jakarta",
        job_company="Beta Ltd",
        job_salary=None,
        job_type="Contract",
        job_posted_date="2026-07-20T08:45:45.47Z",
    )


def test_parse_employment_type_mapping() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@type": "JobPosting",
      "title": "Intern",
      "description": "<p>Learn by doing.</p>",
      "employmentType": "PART_TIME"
    }
    </script>
    </head><body></body></html>
    """
    result = parse(html)
    assert result.job_type == "Part time"
    assert result.job_title == "Intern"
    assert result.job_description == "Learn by doing."


def test_parse_missing_job_posting() -> None:
    html = "<html><body><p>no job fields</p></body></html>"
    with pytest.raises(ValueError, match="missing JobPosting JSON-LD"):
        parse(html)


def test_parse_empty_description() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "X", "description": "   "}
    </script>
    </head><body></body></html>
    """
    with pytest.raises(ValueError, match="missing job description"):
        parse(html)
