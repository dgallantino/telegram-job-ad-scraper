"""Per-site parser modules, one per allowlisted job site.

Every sibling module that exports ``SITE_HOST`` and ``parse`` is auto-
registered into ``SITE_ALLOWLIST``.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

ParserFunc = Callable[[str], dict]

__all__ = ["SITE_ALLOWLIST", "ParserFunc"]

SITE_ALLOWLIST: dict[str, ParserFunc] = {}

for _info in pkgutil.iter_modules(__path__, __name__ + "."):
    _module = importlib.import_module(_info.name)
    _host = getattr(_module, "SITE_HOST", None)
    _parse = getattr(_module, "parse", None)
    if isinstance(_host, str) and callable(_parse):
        SITE_ALLOWLIST[_host.lower().removeprefix("www.")] = _parse
