"""Per-site parser modules, one per allowlisted job site.

Every sibling module that exports ``SITE_HOST`` and ``parse`` is auto-
registered into ``SITE_ALLOWLIST``.
"""

from __future__ import annotations

import importlib
import pkgutil
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


SITE_ALLOWLIST: dict[str, ParserFunc] = {}


for _info in pkgutil.iter_modules(__path__, __name__ + "."):
    _module = importlib.import_module(_info.name)
    _host = getattr(_module, "SITE_HOST", None)
    _parse = getattr(_module, "parse", None)
    if isinstance(_host, str) and callable(_parse):
        SITE_ALLOWLIST[_host.lower().removeprefix("www.")] = _parse


__all__ = ["SITE_ALLOWLIST", "ParserFunc", "JobFields"]