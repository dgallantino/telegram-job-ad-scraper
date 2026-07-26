"""Tests for threads.com / threads.net post HTML parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_scraper.scraper.sites import JobFields
from job_scraper.scraper.sites.threads import parse

_FIXTURES = Path(__file__).parent / "fixtures" / "threads"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_parse_labelled_post() -> None:
    result = parse(_load("post_labelled.html"))
    assert result.job_description.startswith("We're Hiring!")
    assert "Posisi : System Analyst" in result.job_description
    assert "\u200b" not in result.job_description
    assert result == JobFields(
        job_description=result.job_description,
        job_title="System Analyst",
        job_location="Jakarta Barat / Malang (Jawa Timur)",
        job_company="Software House",
        job_salary="Up to IDR 20,000,000",
        job_type=None,
        job_posted_date=None,
    )


def test_parse_positions_list_post() -> None:
    result = parse(_load("post_positions_list.html"))
    assert "Open Positions:" in result.job_description
    assert "https://linkedin.com/in/rendisantoso/" in result.job_description
    assert result.job_title is not None
    assert "Solution Analyst" in result.job_title
    assert "Project Manager" in result.job_title
    assert result.job_company is None
    assert result.job_location is None
    assert result.job_salary == "Competitive & Negotiable"
    assert result.job_posted_date == "ASAP"
    assert result.job_type is None


def test_parse_caption_fallback() -> None:
    result = parse(_load("post_caption_only.html"))
    assert result == JobFields(
        job_description=(
            "We're Hiring!\n\n"
            "Posisi : Backend Engineer\n"
            "Perusahaan : Acme\n"
            "Location : Bandung\n"
            "Salary : Negotiable"
        ),
        job_title="Backend Engineer",
        job_location="Bandung",
        job_company="Acme",
        job_salary="Negotiable",
        job_type=None,
        job_posted_date=None,
    )


def test_parse_missing_post_text_raises() -> None:
    with pytest.raises(ValueError, match="missing Threads post text"):
        parse("<html><head></head><body>empty</body></html>")
