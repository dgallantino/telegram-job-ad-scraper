"""Local JSON state-file persistence.

The only durable state this process keeps outside of Google Sheets is a
small JSON file (mounted on a volume, e.g. ``/data/state.json``) recording at
minimum the last processed Telegram ``update_id``. It is written after each
processed batch of updates, not per message.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TypedDict


class State(TypedDict, total=False):
    """Shape of the state file. Extra keys are preserved but not typed here."""

    last_update_id: int | None


_DEFAULT_STATE: State = {"last_update_id": None}


class StateStore:
    """Load and atomically persist the local JSON state file."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._data: State = dict(_DEFAULT_STATE)

    @property
    def last_update_id(self) -> int | None:
        return self._data.get("last_update_id")

    @last_update_id.setter
    def last_update_id(self, value: int | None) -> None:
        self._data["last_update_id"] = value

    def load(self) -> StateStore:
        """Read the state file into this store, tolerating missing/corrupt files.

        Returns:
            ``self``, for convenient chaining (e.g. ``StateStore(path).load()``).
        """
        if not self._path.exists():
            self._data = dict(_DEFAULT_STATE)
            return self

        try:
            with self._path.open("r", encoding="utf-8") as f:
                data: Any = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = dict(_DEFAULT_STATE)
            return self

        if not isinstance(data, dict):
            self._data = dict(_DEFAULT_STATE)
            return self

        self._data = data
        return self

    def save(self) -> None:
        """Atomically write the state file, creating parent directories as needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, self._path)
