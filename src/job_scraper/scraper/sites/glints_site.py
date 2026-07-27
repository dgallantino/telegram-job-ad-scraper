"""Parser for glints.com job-detail pages.

Fields come from the server-rendered schema.org ``JobPosting`` JSON-LD
block embedded in the page HTML.
"""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from job_scraper.scraper.sites.models import JobFields

SITE_HOST = "glints.com"

_EMPLOYMENT_TYPE_LABELS: dict[str, str] = {
    "FULL_TIME": "Full time",
    "PART_TIME": "Part time",
    "CONTRACTOR": "Contract",
    "CONTRACT": "Contract",
    "TEMPORARY": "Temporary",
    "INTERN": "Internship",
    "INTERNSHIP": "Internship",
}

_UNIT_LABELS: dict[str, str] = {
    "MONTH": "per month",
    "YEAR": "per year",
    "WEEK": "per week",
    "DAY": "per day",
    "HOUR": "per hour",
}


def _as_dict_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _find_job_posting(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _as_dict_list(data):
            if item.get("@type") == "JobPosting":
                return item
    return None


def _html_to_text(html: str) -> str | None:
    text = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
    return text or None


def _str_field(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _location(job: dict[str, Any]) -> str | None:
    place = job.get("jobLocation")
    if isinstance(place, list):
        place = place[0] if place else None
    if not isinstance(place, dict):
        return None
    address = place.get("address")
    if not isinstance(address, dict):
        return None
    parts = [
        part
        for part in (
            _str_field(address.get("addressLocality")),
            _str_field(address.get("addressRegion")),
        )
        if part
    ]
    return ", ".join(parts) or None


def _employment_type(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    raw = _str_field(value)
    if raw is None:
        return None
    key = raw.upper().replace(" ", "_").replace("-", "_")
    if key in _EMPLOYMENT_TYPE_LABELS:
        return _EMPLOYMENT_TYPE_LABELS[key]
    return key.replace("_", " ").title()


def _format_amount(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _salary(job: dict[str, Any]) -> str | None:
    base = job.get("baseSalary")
    if not isinstance(base, dict):
        return None
    currency = _str_field(base.get("currency")) or "IDR"
    value = base.get("value")
    if isinstance(value, (int, float, str)):
        amount = _format_amount(value)
        return f"{currency} {amount}" if amount else None
    if not isinstance(value, dict):
        return None

    min_v = _format_amount(value.get("minValue"))
    max_v = _format_amount(value.get("maxValue"))
    if min_v and max_v and min_v != max_v:
        amount = f"{min_v} – {max_v}"
    else:
        amount = max_v or min_v or _format_amount(value.get("value"))
    if amount is None:
        return None

    unit = _str_field(value.get("unitText"))
    unit_label = _UNIT_LABELS.get(unit.upper(), None) if unit else None
    if unit_label is None and unit:
        unit_label = f"per {unit.lower()}"
    if unit_label:
        return f"{currency} {amount} {unit_label}"
    return f"{currency} {amount}"


def parse(html: str) -> JobFields:
    """Parse a glints.com job-detail page into ``JobFields``.

    Args:
        html: The raw HTML body of the scraped job-detail page.

    Raises:
        ValueError: If the JobPosting JSON-LD or its description is missing.
    """
    soup = BeautifulSoup(html, "lxml")
    job = _find_job_posting(soup)
    if job is None:
        raise ValueError("missing JobPosting JSON-LD")

    description_html = job.get("description")
    if not isinstance(description_html, str) or not description_html.strip():
        raise ValueError("missing job description")
    job_description = _html_to_text(description_html)
    if job_description is None:
        raise ValueError("missing job description")

    org = job.get("hiringOrganization")
    company = _str_field(org.get("name")) if isinstance(org, dict) else None

    return JobFields(
        job_description=job_description,
        job_title=_str_field(job.get("title")),
        job_location=_location(job),
        job_company=company,
        job_salary=_salary(job),
        job_type=_employment_type(job.get("employmentType")),
        job_posted_date=_str_field(job.get("datePosted")),
    )
