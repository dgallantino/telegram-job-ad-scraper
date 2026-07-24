"""Sheet A read/write client, backed by ``gspread`` + ``google-auth``.

Sheet A columns: ``job_id`` (string ``{chat_id}_{message_id}``), ``timestamp``,
``url``, ``crawl_status`` (``pending``/``running``/``finished``/``failed``/
``rejected``), ``job_title``, ``job_description``, ``job_location``,
``job_company``, ``job_salary``, ``job_type``, ``job_posted_date``.

This module only defines the client construction and method signatures.
Reads/writes are batched deliberately — Sheets API has real rate limits, so
callers should avoid per-message synchronous writes. The full
reconciliation-from-Sheet-A logic (deriving a resume point when the local
state file is missing/corrupt) is not implemented here yet.
"""

from __future__ import annotations

from typing import Any

from job_scrapper.config import Settings

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


class SheetsClient:
    """Thin wrapper around a ``gspread`` worksheet handle for Sheet A."""

    def __init__(self, settings: Settings) -> None:
        """Store settings needed to authenticate and open Sheet A.

        TODO: Authenticate with ``google.oauth2.service_account.Credentials``
        using ``settings.google_service_account_key``, build a ``gspread``
        client, and open the worksheet identified by
        ``settings.google_sheets_spreadsheet_id`` /
        ``settings.google_sheets_sheet_name``. Not connecting yet.
        """
        self._settings = settings

    def append_pending_row(self, job_id: str, timestamp: str, url: str) -> None:
        """Append a new row with ``crawl_status = pending`` for an accepted URL.

        TODO: Implement with a batched ``append_row``/``append_rows`` call.
        """
        raise NotImplementedError

    def append_rejected_row(self, job_id: str, timestamp: str, url: str, reason: str) -> None:
        """Append a row with ``crawl_status = rejected`` for audit purposes.

        Rejected/unsupported URLs still get a row — they are never silently
        dropped after replying in chat.

        TODO: Implement with a batched write.
        """
        raise NotImplementedError

    def update_status(self, job_id: str, crawl_status: str) -> None:
        """Update only the ``crawl_status`` cell for ``job_id`` (e.g. to ``running``).

        TODO: Implement — look up the row for ``job_id`` and update in place.
        """
        raise NotImplementedError

    def update_result(self, job_id: str, crawl_status: str, fields: dict[str, Any]) -> None:
        """Write parsed job fields plus a terminal ``crawl_status`` for ``job_id``.

        Args:
            job_id: The row to update.
            crawl_status: ``finished`` or ``failed``.
            fields: A subset of the ``job_*`` columns from ``SHEET_A_COLUMNS``.

        TODO: Implement with a single batched row update.
        """
        raise NotImplementedError

    def list_incomplete_jobs(self) -> list[dict[str, Any]]:
        """Return all rows with ``crawl_status`` in (``pending``, ``running``).

        Used on startup to re-enqueue jobs that were in flight during a
        previous crash, and as a best-effort fallback for reconciliation
        when the local state file is missing or corrupt.

        TODO: Implement with a single batched read of the worksheet.
        """
        raise NotImplementedError
