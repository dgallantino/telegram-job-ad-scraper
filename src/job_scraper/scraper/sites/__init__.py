"""Per-site parser modules, one per allowlisted job site.

Every sibling module that exports ``SITE_HOST`` (or ``SITE_HOSTS``) and
``parse`` is auto-registered into ``SITE_ALLOWLIST``. Optional
``FETCH_USER_AGENT`` is recorded in ``SITE_FETCH_USER_AGENTS``.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Iterable
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
SITE_FETCH_USER_AGENTS: dict[str, str] = {}


def _iter_hosts(module: object) -> Iterable[str]:
    hosts = getattr(module, "SITE_HOSTS", None)
    if isinstance(hosts, (list, tuple)):
        for host in hosts:
            if isinstance(host, str) and host:
                yield host
        return
    host = getattr(module, "SITE_HOST", None)
    if isinstance(host, str) and host:
        yield host


for _info in pkgutil.iter_modules(__path__, __name__ + "."):
    _module = importlib.import_module(_info.name)
    _parse = getattr(_module, "parse", None)
    if not callable(_parse):
        continue
    _ua = getattr(_module, "FETCH_USER_AGENT", None)
    for _host in _iter_hosts(_module):
        _key = _host.lower().removeprefix("www.")
        SITE_ALLOWLIST[_key] = _parse
        if isinstance(_ua, str) and _ua:
            SITE_FETCH_USER_AGENTS[_key] = _ua


__all__ = [
    "SITE_ALLOWLIST",
    "SITE_FETCH_USER_AGENTS",
    "ParserFunc",
    "JobFields",
]
