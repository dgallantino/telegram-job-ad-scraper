"""Tests for id.jobstreet.com job-detail HTML parsing."""

from __future__ import annotations

from pathlib import Path

from job_scraper.scraper.sites.jobstreet import parse

_FIXTURES = Path(__file__).parent / "fixtures" / "jobstreet"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_parse_full_fixture() -> None:
    result = parse(_load("detail_full.html"))
    assert result == {
        "job_title": "Senior Python Engineer",
        "job_description": "Build scrapers and bots.",
        "job_location": "Jakarta",
        "job_company": "Acme Corp",
        "job_salary": "Rp 15.000.000 – 20.000.000 per month",
        "job_type": "Full time",
        "job_posted_date": "2026-07-01T08:00:00.000Z",
    }


def test_parse_dom_only_no_apollo() -> None:
    result = parse(_load("detail_dom_only.html"))
    assert result == {
        "job_title": "Backend Developer",
        "job_description": "Ship APIs.",
        "job_location": "Bandung",
        "job_company": "Beta Ltd",
        "job_salary": None,
        "job_type": "Contract",
        "job_posted_date": None,
    }


def test_parse_malformed_apollo_keeps_dom_fields() -> None:
    result = parse(_load("detail_apollo_malformed.html"))
    assert result == {
        "job_title": "QA Engineer",
        "job_description": "Test everything.",
        "job_location": "Surabaya",
        "job_company": "Gamma Inc",
        "job_salary": None,
        "job_type": "Part time",
        "job_posted_date": None,
    }


def test_parse_graphql_style_salary_label() -> None:
    html = """
    <html><body>
      <h1 data-automation="job-detail-title">DevOps</h1>
      <script>
        window.SEEK_APOLLO_DATA = {
          "ROOT_QUERY": {
            "jobDetails": {
              "job": {
                "__typename": "Job",
                "listedAt": {"dateTimeUtc": "2026-06-15T12:00:00.000Z"},
                "salary": {"label({\\"locale\\":\\"id-ID\\"})": "Rp 12jt"}
              }
            }
          }
        };
      </script>
    </body></html>
    """
    result = parse(html)
    assert result["job_title"] == "DevOps"
    assert result["job_salary"] == "Rp 12jt"
    assert result["job_posted_date"] == "2026-06-15T12:00:00.000Z"


def test_parse_missing_automation_nodes() -> None:
    html = "<html><body><p>no job fields</p></body></html>"
    result = parse(html)
    assert result == {
        "job_title": None,
        "job_description": None,
        "job_location": None,
        "job_company": None,
        "job_salary": None,
        "job_type": None,
        "job_posted_date": None,
    }
