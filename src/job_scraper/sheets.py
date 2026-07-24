"""``jobs`` worksheet read/write client, backed by ``gspread`` + ``google-auth``.

Columns: ``job_id`` (string ``{chat_id}_{message_id}``), ``timestamp``,
``url``, ``crawl_status`` (``pending``/``running``/``finished``/``failed``/
``rejected``), ``job_title``, ``job_description``, ``job_location``,
``job_company``, ``job_salary``, ``job_type``, ``job_posted_date``.

Each public method uses a single gspread write/read call where practical
(Sheets API rate limits). Callers still invoke methods per message — there
is no write buffer here.

Startup re-enqueue of ``pending``/``running`` rows and update-id
reconciliation from the sheet belong in ``main.py``; this module only
exposes ``list_incomplete_jobs`` for those callers.
"""

from __future__ import annotations

from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

from job_scraper.config import Settings

CRAWL_STATUS_PENDING = "pending"
CRAWL_STATUS_RUNNING = "running"
CRAWL_STATUS_FINISHED = "finished"
CRAWL_STATUS_FAILED = "failed"
CRAWL_STATUS_REJECTED = "rejected"

SHEET_A_COLUMNS = (
    "job_id",
    "timestamp",
    "url",
    "crawl_status",
    "job_title",
    "job_description",
    "job_location",
    "job_company",
    "job_salary",
    "job_type",
    "job_posted_date",
)

_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)

_JOB_FIELD_COLUMNS = frozenset(
    name for name in SHEET_A_COLUMNS if name.startswith("job_")
)

_COL_JOB_ID = SHEET_A_COLUMNS.index("job_id") + 1
_COL_CRAWL_STATUS = SHEET_A_COLUMNS.index("crawl_status") + 1


class JobNotFoundError(LookupError):
    """Raised when no ``jobs`` row matches the given ``job_id``."""


class SheetsClient:
    """Thin wrapper around a ``gspread`` worksheet handle for the ``jobs`` sheet."""

    def __init__(self, settings: Settings) -> None:
        """Authenticate with the service-account key and open the ``jobs`` worksheet.

        ``settings.google_service_account_key`` is a path to the JSON key file.
        Ensures row 1 matches ``SHEET_A_COLUMNS`` on connect.
        """
        self._settings = settings
        credentials = Credentials.from_service_account_file(
            settings.google_service_account_key,
            scopes=_SCOPES,
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(settings.google_sheets_spreadsheet_id)
        self._worksheet = spreadsheet.worksheet(settings.google_sheets_sheet_name)
        self._ensure_header()

    def _ensure_header(self) -> None:
        """Write ``SHEET_A_COLUMNS`` to row 1 if missing or mismatched."""
        header = self._worksheet.row_values(1)
        expected = list(SHEET_A_COLUMNS)
        if header == expected:
            return
        self._worksheet.update([expected], "A1", raw=False)

    def _empty_job_fields(self) -> list[str]:
        return [""] * (len(SHEET_A_COLUMNS) - 4)

    def _build_row(
        self, job_id: str, timestamp: str, url: str, crawl_status: str
    ) -> list[str]:
        return [job_id, timestamp, url, crawl_status, *self._empty_job_fields()]

    def _find_row_number(self, job_id: str) -> int:
        """Return 1-based row index for ``job_id``, or raise ``JobNotFoundError``."""
        # col_values includes the header at index 0 when present.
        values = self._worksheet.col_values(_COL_JOB_ID)
        for index, value in enumerate(values):
            if index == 0:
                continue
            if value == job_id:
                return index + 1
        raise JobNotFoundError(f"No jobs row found for job_id={job_id!r}")

    def append_pending_row(self, job_id: str, timestamp: str, url: str) -> None:
        """Append a new row with ``crawl_status = pending`` for an accepted URL."""
        self._worksheet.append_row(
            self._build_row(job_id, timestamp, url, CRAWL_STATUS_PENDING),
            value_input_option="USER_ENTERED",
        )

    def append_rejected_row(
        self, job_id: str, timestamp: str, url: str, reason: str
    ) -> None:
        """Append a row with ``crawl_status = rejected`` for audit purposes.

        Rejected/unsupported URLs still get a row — they are never silently
        dropped after replying in chat. ``reason`` is accepted for the caller
        API but is intentionally not persisted (no column for it).
        """
        del reason  # kept for API compatibility; not written to the sheet
        self._worksheet.append_row(
            self._build_row(job_id, timestamp, url, CRAWL_STATUS_REJECTED),
            value_input_option="USER_ENTERED",
        )

    def update_status(self, job_id: str, crawl_status: str) -> None:
        """Update only the ``crawl_status`` cell for ``job_id`` (e.g. to ``running``).

        Raises:
            JobNotFoundError: If no row with ``job_id`` exists.
        """
        row = self._find_row_number(job_id)
        cell = rowcol_to_a1(row, _COL_CRAWL_STATUS)
        self._worksheet.update([[crawl_status]], cell, raw=False)

    def update_result(
        self, job_id: str, crawl_status: str, fields: dict[str, Any]
    ) -> None:
        """Write parsed job fields plus a terminal ``crawl_status`` for ``job_id``.

        Args:
            job_id: The row to update.
            crawl_status: ``finished`` or ``failed``.
            fields: A subset of the ``job_*`` columns from ``SHEET_A_COLUMNS``.
                Unknown keys are ignored.

        Raises:
            JobNotFoundError: If no row with ``job_id`` exists.
        """
        row = self._find_row_number(job_id)
        updates: list[dict[str, Any]] = [
            {
                "range": rowcol_to_a1(row, _COL_CRAWL_STATUS),
                "values": [[crawl_status]],
            }
        ]
        for name, value in fields.items():
            if name not in _JOB_FIELD_COLUMNS:
                continue
            col = SHEET_A_COLUMNS.index(name) + 1
            updates.append(
                {
                    "range": rowcol_to_a1(row, col),
                    "values": [[value if value is not None else ""]],
                }
            )
        self._worksheet.batch_update(updates, raw=False)

    def list_incomplete_jobs(self) -> list[dict[str, Any]]:
        """Return all rows with ``crawl_status`` in (``pending``, ``running``).

        Used by ``main.py`` on startup to re-enqueue jobs that were in flight
        during a previous crash, and as a best-effort fallback for
        reconciliation when the local state file is missing or corrupt.
        """
        rows = self._worksheet.get_all_records()
        incomplete = (CRAWL_STATUS_PENDING, CRAWL_STATUS_RUNNING)
        return [row for row in rows if row.get("crawl_status") in incomplete]
