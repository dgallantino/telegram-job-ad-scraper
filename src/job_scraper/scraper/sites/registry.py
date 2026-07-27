"""Auto-register ``*_site`` parser modules into the allowlist.

Every sibling module whose name ends with ``_site`` and that exports
``SITE_HOST`` (or ``SITE_HOSTS``) and ``parse`` is registered into
``SITE_ALLOWLIST``. Optional ``FETCH_USER_AGENT`` is recorded in
``SITE_FETCH_USER_AGENTS``.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable

from job_scraper.scraper import sites as sites_pkg
from job_scraper.scraper.sites.models import ParserFunc

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


for _info in pkgutil.iter_modules(sites_pkg.__path__, sites_pkg.__name__ + "."):
    _short = _info.name.rsplit(".", 1)[-1]
    if not _short.endswith("_site"):
        continue
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
