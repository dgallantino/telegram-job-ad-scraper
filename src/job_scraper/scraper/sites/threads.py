"""Parser for threads.com / threads.net post pages.

Threads job ads are unstructured free text. The post body comes from
SSR ``og:description`` (or embedded ``caption.text`` as fallback). Optional
sheet fields are filled via the tunable ``_FIELD_REGEXES`` map below.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from job_scraper.scraper.sites import JobFields

SITE_HOSTS = ("threads.com", "threads.net")

# Chrome UA gets a JS shell with no post body; link-preview crawlers get SSR.
FETCH_USER_AGENT = (
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
)

_CAPTION_TEXT_RE = re.compile(r'"caption"\s*:\s*\{\s*"text"\s*:\s*"')

# First matching pattern per field wins. Tune against new posts here.
_FIELD_REGEXES: dict[str, tuple[re.Pattern[str], ...]] = {
    "job_title": (
        re.compile(r"(?im)^Posisi\s*:\s*(.+)$"),
        re.compile(r"(?im)^📌?\s*Open Positions?\s*:\s*\n((?:[•\-\*].+\n?)+)"),
    ),
    "job_company": (
        re.compile(r"(?im)^Perusahaan\s*:\s*(.+)$"),
        re.compile(r"(?im)^Company\s*:\s*(.+)$"),
    ),
    "job_location": (
        re.compile(r"(?im)^Location\s*:\s*(.+)$"),
        re.compile(r"(?im)^Lokasi\s*:\s*(.+)$"),
    ),
    "job_salary": (
        re.compile(r"(?im)^(?:💰\s*)?Salary\s*:\s*(.+)$"),
        re.compile(r"(?im)^Gaji\s*:\s*(.+)$"),
    ),
    "job_type": (
        re.compile(r"(?im)^(?:Job\s*)?Type\s*:\s*(.+)$"),
        re.compile(r"(?im)^Tipe(?:\s*pekerjaan)?\s*:\s*(.+)$"),
    ),
    "job_posted_date": (
        re.compile(r"(?im)^(?:📅\s*)?(?:Start Date|Posted|Tanggal)\s*:\s*(.+)$"),
    ),
}


def _strip_zwsp(text: str) -> str:
    return text.replace("\u200b", "")


def _og_description(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    el = soup.find("meta", property="og:description")
    if el is None:
        return None
    content = el.get("content")
    if not isinstance(content, str):
        return None
    text = content.strip()
    return text or None


def _caption_text(html: str) -> str | None:
    """Extract ``"caption":{"text":"..."}`` from embedded page JSON."""
    match = _CAPTION_TEXT_RE.search(html)
    if match is None:
        return None
    start = match.end()
    # Walk the JSON string literal starting at ``start``.
    chars: list[str] = []
    i = start
    escaped = False
    while i < len(html):
        ch = html[i]
        if escaped:
            chars.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\":
            chars.append(ch)
            escaped = True
            i += 1
            continue
        if ch == '"':
            break
        chars.append(ch)
        i += 1
    else:
        return None
    try:
        text = json.loads('"' + "".join(chars) + '"')
    except json.JSONDecodeError:
        return None
    if not isinstance(text, str):
        return None
    text = text.strip()
    return text or None


def _extract_post_text(html: str) -> str:
    text = _og_description(html)
    if text is None:
        text = _caption_text(html)
    if text is None:
        raise ValueError("missing Threads post text (og:description / caption.text)")
    return _strip_zwsp(text)


def _first_match(text: str, patterns: tuple[re.Pattern[str], ...]) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match is None:
            continue
        value = match.group(1).strip()
        if value:
            return value
    return None


def parse(html: str) -> JobFields:
    """Parse a Threads post page into ``JobFields``.

    Args:
        html: The raw HTML body of the scraped post page.

    Raises:
        ValueError: If the post text cannot be found.
    """
    job_description = _extract_post_text(html)

    fields: dict[str, str | None] = {
        name: _first_match(job_description, patterns)
        for name, patterns in _FIELD_REGEXES.items()
    }

    return JobFields(
        job_description=job_description,
        job_title=fields.get("job_title"),
        job_location=fields.get("job_location"),
        job_company=fields.get("job_company"),
        job_salary=fields.get("job_salary"),
        job_type=fields.get("job_type"),
        job_posted_date=fields.get("job_posted_date"),
    )
