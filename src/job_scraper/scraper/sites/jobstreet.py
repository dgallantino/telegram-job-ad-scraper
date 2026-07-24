"""Parser for id.jobstreet.com job-detail pages.

Primary fields come from stable ``data-automation`` DOM attributes.
``job_posted_date`` and ``job_salary`` are taken from the embedded
``window.SEEK_APOLLO_DATA`` job node when present.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

SITE_HOST = "id.jobstreet.com"

_WINDOW_ASSIGN_RE = re.compile(
    r"window\.(?P<name>[A-Za-z0-9_]+)\s*=\s*",
)


def _automation_text(soup: BeautifulSoup, name: str) -> str | None:
    el = soup.select_one(f'[data-automation="{name}"]')
    if el is None:
        return None
    text = el.get_text("\n", strip=True)
    return text or None


def _extract_window_json(html: str, name: str) -> dict[str, Any] | None:
    """Parse ``window.<name> = {...};`` via brace matching."""
    for match in _WINDOW_ASSIGN_RE.finditer(html):
        if match.group("name") != name:
            continue
        start = match.end()
        while start < len(html) and html[start] in " \t\n\r":
            start += 1
        if start >= len(html) or html[start] != "{":
            return None
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(html[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(html[start : i + 1])
                    except json.JSONDecodeError:
                        return None
                    return data if isinstance(data, dict) else None
        return None
    return None


def _gql_field(obj: dict[str, Any], prefix: str) -> Any:
    """Return ``obj[prefix]`` or the first key that starts with ``prefix(``."""
    if prefix in obj:
        return obj[prefix]
    needle = f"{prefix}("
    for key, value in obj.items():
        if key.startswith(needle):
            return value
    return None


def _apollo_job(apollo: dict[str, Any]) -> dict[str, Any] | None:
    """Find the normalized Job node under ``ROOT_QUERY`` jobDetails."""
    root = apollo.get("ROOT_QUERY")
    if not isinstance(root, dict):
        return None
    for key, value in root.items():
        if not key.startswith("jobDetails"):
            continue
        if not isinstance(value, dict):
            continue
        job = value.get("job")
        if isinstance(job, dict) and job.get("__typename") == "Job":
            return job
        if isinstance(job, dict) and "listedAt" in job:
            return job
    return None


def _salary_value(salary: Any) -> str | None:
    if salary is None:
        return None
    if isinstance(salary, str):
        return salary or None
    if isinstance(salary, dict):
        label = _gql_field(salary, "label")
        if isinstance(label, str) and label:
            return label
        # Fall back to a compact JSON dump only if somehow structured.
        return None
    return str(salary) if salary else None


def parse(html: str) -> dict:
    """Parse an id.jobstreet.com job-detail page into ``jobs`` sheet fields.

    Args:
        html: The raw HTML body of the scraped job-detail page.
    """
    soup = BeautifulSoup(html, "lxml")

    job_title = _automation_text(soup, "job-detail-title")
    job_company = _automation_text(soup, "advertiser-name")
    job_location = _automation_text(soup, "job-detail-location")
    job_type = _automation_text(soup, "job-detail-work-type")
    job_description = _automation_text(soup, "jobAdDetails")

    job_posted_date: str | None = None
    job_salary: str | None = None

    apollo = _extract_window_json(html, "SEEK_APOLLO_DATA")
    if apollo is not None:
        job = _apollo_job(apollo)
        if job is not None:
            listed_at = job.get("listedAt")
            if isinstance(listed_at, dict):
                dt = listed_at.get("dateTimeUtc")
                if isinstance(dt, str) and dt:
                    job_posted_date = dt
            job_salary = _salary_value(job.get("salary"))

    return {
        "job_title": job_title,
        "job_description": job_description,
        "job_location": job_location,
        "job_company": job_company,
        "job_salary": job_salary,
        "job_type": job_type,
        "job_posted_date": job_posted_date,
    }

