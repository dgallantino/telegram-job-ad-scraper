"""Tests for Threads LLM field-extraction fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_scraper.scraper.sites.llm_extractor import LlmExtractorError
from job_scraper.scraper.sites.threads_site import parse

_FIXTURES = Path(__file__).parent / "fixtures" / "threads"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_llm_fills_only_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """positions_list fixture: regex finds title/salary/date; company/location/type miss."""

    def fake_extract(*, input_text: str, schema: dict, **kwargs: object) -> dict:
        # Schema should only ask for missing keys.
        props = schema.get("properties", {})
        assert "job_company" in props
        assert "job_location" in props
        assert "job_type" in props
        assert "job_title" not in props  # already filled by regex
        assert "job_salary" not in props
        return {
            "job_company": "Acme Corp",
            "job_location": None,
            "job_type": "  Full-time  ",
        }

    monkeypatch.setattr(
        "job_scraper.scraper.sites.threads_site.extract_with_json_schema",
        fake_extract,
    )

    result = parse(_load("post_positions_list.html"))
    assert "Solution Analyst" in (result.job_title or "")
    assert result.job_salary == "Competitive & Negotiable"
    assert result.job_posted_date == "ASAP"
    assert result.job_company == "Acme Corp"
    assert result.job_type == "Full-time"
    assert result.job_location is None  # null from LLM ignored


def test_llm_failure_keeps_regex_results(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*, input_text: str, schema: dict, **kwargs: object) -> dict:
        raise LlmExtractorError("simulated failure")

    monkeypatch.setattr(
        "job_scraper.scraper.sites.threads_site.extract_with_json_schema",
        boom,
    )

    result = parse(_load("post_positions_list.html"))
    assert result.job_title is not None
    assert "Solution Analyst" in result.job_title
    assert result.job_salary == "Competitive & Negotiable"
    assert result.job_posted_date == "ASAP"
    assert result.job_company is None
    assert result.job_location is None
    assert result.job_type is None


def test_llm_not_called_when_all_fields_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """labelled fixture fills title/company/location/salary; type/date still missing.

    Use a custom HTML where every regex field matches so LLM is skipped.
    """
    spy = MagicMock(return_value={})
    monkeypatch.setattr(
        "job_scraper.scraper.sites.threads_site.extract_with_json_schema",
        spy,
    )

    html = """
    <html><head>
    <meta property="og:description" content="We're Hiring!
Posisi : Backend Engineer
Perusahaan : Acme
Location : Bandung
Salary : Negotiable
Type : Full-time
Posted : 2024-01-01
" />
    </head><body></body></html>
    """
    result = parse(html)
    assert result.job_title == "Backend Engineer"
    assert result.job_company == "Acme"
    assert result.job_location == "Bandung"
    assert result.job_salary == "Negotiable"
    assert result.job_type == "Full-time"
    assert result.job_posted_date == "2024-01-01"
    spy.assert_not_called()


def test_llm_does_not_overwrite_regex_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_extract(*, input_text: str, schema: dict, **kwargs: object) -> dict:
        # Even if the model returns a key that was already filled, merge
        # only iterates over ``missing``, so regex wins.
        return {
            "job_title": "SHOULD NOT APPLY",
            "job_type": "Contract",
        }

    monkeypatch.setattr(
        "job_scraper.scraper.sites.threads_site.extract_with_json_schema",
        fake_extract,
    )

    result = parse(_load("post_labelled.html"))
    assert result.job_title == "System Analyst"
    assert result.job_company == "Software House"
    assert result.job_type == "Contract"
