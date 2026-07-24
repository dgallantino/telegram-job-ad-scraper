"""Environment-variable loading and validation for the job scraper.

Reads configuration from the process environment (optionally populated from a
local ``.env`` file via ``python-dotenv``) into a single immutable
``Settings`` object. Required secrets/IDs are validated eagerly so the process
fails fast on startup rather than deep inside the event loop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_REQUIRED_VARS = (
    "GOOGLE_SERVICE_ACCOUNT_KEY",
    "GOOGLE_SHEETS_SPREADSHEET_ID",
    "GOOGLE_SHEETS_SHEET_NAME",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
)

_DEFAULT_STATE_FILE_PATH = "/data/state.json"
_DEFAULT_WORKER_COUNT = 1
_DEFAULT_TELEGRAM_POLL_TIMEOUT = 30


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Fully-resolved application configuration."""

    google_service_account_key: str
    google_sheets_spreadsheet_id: str
    google_sheets_sheet_name: str
    telegram_bot_token: str
    telegram_chat_id: str
    state_file_path: str
    worker_count: int
    telegram_poll_timeout: int


def load_settings(env_file: str | None = None) -> Settings:
    """Load and validate settings from the environment.

    Args:
        env_file: Optional explicit path to a ``.env`` file. If omitted,
            ``python-dotenv`` searches upward from the current working
            directory for a ``.env`` file (a no-op if none is found, e.g. in
            production where real env vars/secrets are injected directly).

    Raises:
        ConfigError: If a required variable is missing, or a numeric
            variable cannot be parsed.
    """
    load_dotenv(dotenv_path=env_file)

    missing = [name for name in _REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}"
        )

    worker_count = _parse_int(
        "WORKER_COUNT", os.environ.get("WORKER_COUNT"), _DEFAULT_WORKER_COUNT
    )
    telegram_poll_timeout = _parse_int(
        "TELEGRAM_POLL_TIMEOUT",
        os.environ.get("TELEGRAM_POLL_TIMEOUT"),
        _DEFAULT_TELEGRAM_POLL_TIMEOUT,
    )

    return Settings(
        google_service_account_key=os.environ["GOOGLE_SERVICE_ACCOUNT_KEY"],
        google_sheets_spreadsheet_id=os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"],
        google_sheets_sheet_name=os.environ["GOOGLE_SHEETS_SHEET_NAME"],
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
        state_file_path=os.environ.get("STATE_FILE_PATH", _DEFAULT_STATE_FILE_PATH),
        worker_count=worker_count,
        telegram_poll_timeout=telegram_poll_timeout,
    )


def _parse_int(name: str, raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer, got: {raw!r}") from exc
