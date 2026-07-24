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


def load_state(path: str) -> State:
    """Read the state file, tolerating a missing or corrupt file.

    Returns:
        The parsed state dict, or a copy of the default state if the file
        does not exist or cannot be parsed as valid JSON.
    """
    file_path = Path(path)
    if not file_path.exists():
        return dict(_DEFAULT_STATE)

    try:
        with file_path.open("r", encoding="utf-8") as f:
            data: Any = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_STATE)

    if not isinstance(data, dict):
        return dict(_DEFAULT_STATE)

    return data


def save_state(path: str, state: State) -> None:
    """Atomically write the state file, creating parent directories as needed."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp_path, file_path)
