"""Shared types for per-site parsers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class JobFields:
    """Parsed job-ad fields written to the ``jobs`` sheet ``job_*`` columns.

    ``job_description`` is required; all other fields are optional.
    """

    job_description: str
    job_title: str | None = None
    job_location: str | None = None
    job_company: str | None = None
    job_salary: str | None = None
    job_type: str | None = None
    job_posted_date: str | None = None


ParserFunc = Callable[[str], JobFields]
