"""Parser for threads.com / threads.net post pages.

Threads job ads are unstructured free text. The post body comes from
SSR ``og:description`` (or embedded ``caption.text`` as fallback). Optional
sheet fields are filled via the tunable ``_FIELD_REGEXES`` map below.
Fields still missing after regex may be filled by an optional LLM fallback
(see ``llm_extractor``); that path is non-critical and fail-silent.
"""

from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from job_scraper.scraper.sites.llm_extractor import extract_with_json_schema
from job_scraper.scraper.sites.models import JobFields

logger = logging.getLogger(__name__)

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

_FIELD_DESCRIPTIONS: dict[str, str] = {
    "job_title": "Job title or open positions listed in the post",
    "job_company": "Company or employer name",
    "job_location": "Work location / city",
    "job_salary": "Salary or compensation range",
    "job_type": "Employment type (full-time, contract, etc.)",
    "job_posted_date": "Posted date, start date, or similar date label",
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


def _build_missing_fields_schema(missing: list[str]) -> dict:
    """JSON schema covering only the keys still unset after regex."""
    properties = {
        key: {
            "type": ["string", "null"],
            "description": _FIELD_DESCRIPTIONS.get(key, key),
        }
        for key in missing
    }
    return {
        "type": "object",
        "properties": properties,
        "required": [],
        "additionalProperties": False,
    }


def _build_llm_prompt(job_description: str, missing: list[str]) -> str:
    field_list = ", ".join(missing)
    return (
        "Extract job-ad fields from the Threads post text below.\n"
        "\n"
        "Rules:\n"
        f"- The following fields are optional: {field_list}.\n"
        "- Extract ONLY values that are explicitly present in the post text.\n"
        "- Do NOT invent, guess, or infer values that are not written in the text.\n"
        "- If a field is not found, omit it or return null.\n"
        "- Your job is extraction only — not filling every field.\n"
        "\n"
        "Post text:\n"
        "---\n"
        f"{job_description}\n"
        "---\n"
    )


def _fill_missing_with_llm(
    job_description: str,
    fields: dict[str, str | None],
    missing: list[str],
) -> None:
    """Fill ``fields`` in-place for keys in ``missing`` using the LLM.

    Only non-empty string values from the model are written; regex hits are
    never overwritten.
    """
    schema = _build_missing_fields_schema(missing)
    prompt = _build_llm_prompt(job_description, missing)
    extracted = extract_with_json_schema(
        input_text=prompt,
        schema=schema,
        schema_name="threads_job_fields",
    )
    for key in missing:
        value = extracted.get(key)
        if isinstance(value, str):
            value = value.strip()
            if value:
                fields[key] = value


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

    missing = [key for key, value in fields.items() if value is None]
    if missing:
        try:
            _fill_missing_with_llm(job_description, fields, missing)
        except Exception:  # noqa: BLE001 - LLM is non-critical; keep regex results
            logger.exception("threads LLM field extraction failed")

    return JobFields(
        job_description=job_description,
        job_title=fields.get("job_title"),
        job_location=fields.get("job_location"),
        job_company=fields.get("job_company"),
        job_salary=fields.get("job_salary"),
        job_type=fields.get("job_type"),
        job_posted_date=fields.get("job_posted_date"),
    )
