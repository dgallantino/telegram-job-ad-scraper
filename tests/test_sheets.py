"""Tests for SheetsClient (mocked gspread; no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from job_scrapper.config import Settings
from job_scrapper.sheets import (
    CRAWL_STATUS_FAILED,
    CRAWL_STATUS_FINISHED,
    CRAWL_STATUS_PENDING,
    CRAWL_STATUS_REJECTED,
    CRAWL_STATUS_RUNNING,
    SHEET_A_COLUMNS,
    JobNotFoundError,
    SheetsClient,
)


def _settings(tmp_path: Path) -> Settings:
    key_path = tmp_path / "sa.json"
    key_path.write_text("{}", encoding="utf-8")
    return Settings(
        google_service_account_key=str(key_path),
        google_sheets_spreadsheet_id="sheet-id",
        google_sheets_sheet_name="jobs",
        telegram_bot_token="123:ABC",
        telegram_chat_id="-100123",
        state_file_path=str(tmp_path / "state.json"),
        worker_count=1,
        telegram_poll_timeout=1,
    )


def _make_client(
    tmp_path: Path,
    *,
    header: list[str] | None = None,
    col_job_ids: list[str] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> tuple[SheetsClient, MagicMock]:
    worksheet = MagicMock()
    worksheet.row_values.return_value = (
        list(SHEET_A_COLUMNS) if header is None else header
    )
    worksheet.col_values.return_value = col_job_ids if col_job_ids is not None else []
    worksheet.get_all_records.return_value = records if records is not None else []

    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = worksheet

    client = MagicMock()
    client.open_by_key.return_value = spreadsheet

    credentials = MagicMock()
    with (
        patch(
            "job_scrapper.sheets.Credentials.from_service_account_file",
            return_value=credentials,
        ),
        patch("job_scrapper.sheets.gspread.authorize", return_value=client),
    ):
        sheets = SheetsClient(_settings(tmp_path))

    return sheets, worksheet


def test_ensure_header_writes_when_empty(tmp_path: Path) -> None:
    _, worksheet = _make_client(tmp_path, header=[])
    worksheet.update.assert_called_once_with([list(SHEET_A_COLUMNS)], "A1", raw=False)


def test_ensure_header_skips_when_correct(tmp_path: Path) -> None:
    _, worksheet = _make_client(tmp_path, header=list(SHEET_A_COLUMNS))
    worksheet.update.assert_not_called()


def test_ensure_header_rewrites_when_mismatched(tmp_path: Path) -> None:
    _, worksheet = _make_client(tmp_path, header=["wrong", "cols"])
    worksheet.update.assert_called_once_with([list(SHEET_A_COLUMNS)], "A1", raw=False)


def test_append_pending_row(tmp_path: Path) -> None:
    sheets, worksheet = _make_client(tmp_path)
    worksheet.reset_mock()

    sheets.append_pending_row("-100_1", "2026-01-01T00:00:00Z", "https://example.com/j")

    worksheet.append_row.assert_called_once()
    row = worksheet.append_row.call_args.args[0]
    assert row[0] == "-100_1"
    assert row[1] == "2026-01-01T00:00:00Z"
    assert row[2] == "https://example.com/j"
    assert row[3] == CRAWL_STATUS_PENDING
    assert len(row) == len(SHEET_A_COLUMNS)
    assert all(cell == "" for cell in row[4:])


def test_append_rejected_row_ignores_reason(tmp_path: Path) -> None:
    sheets, worksheet = _make_client(tmp_path)
    worksheet.reset_mock()

    sheets.append_rejected_row(
        "-100_2",
        "2026-01-01T00:00:00Z",
        "https://bad.example/j",
        "unsupported site",
    )

    row = worksheet.append_row.call_args.args[0]
    assert row[3] == CRAWL_STATUS_REJECTED
    assert "unsupported site" not in row
    assert len(row) == len(SHEET_A_COLUMNS)


def test_update_status(tmp_path: Path) -> None:
    sheets, worksheet = _make_client(
        tmp_path,
        col_job_ids=["job_id", "-100_1", "-100_2"],
    )
    worksheet.reset_mock()
    worksheet.col_values.return_value = ["job_id", "-100_1", "-100_2"]

    sheets.update_status("-100_2", CRAWL_STATUS_RUNNING)

    worksheet.update.assert_called_once_with(
        [[CRAWL_STATUS_RUNNING]], "D3", raw=False
    )


def test_update_status_missing_raises(tmp_path: Path) -> None:
    sheets, worksheet = _make_client(
        tmp_path,
        col_job_ids=["job_id", "-100_1"],
    )
    worksheet.col_values.return_value = ["job_id", "-100_1"]

    with pytest.raises(JobNotFoundError, match="missing"):
        sheets.update_status("missing", CRAWL_STATUS_RUNNING)


def test_update_result_batch_and_ignores_unknown(tmp_path: Path) -> None:
    sheets, worksheet = _make_client(
        tmp_path,
        col_job_ids=["job_id", "j1"],
    )
    worksheet.reset_mock()
    worksheet.col_values.return_value = ["job_id", "j1"]

    sheets.update_result(
        "j1",
        CRAWL_STATUS_FINISHED,
        {
            "job_title": "Engineer",
            "job_company": "Acme",
            "unknown_field": "nope",
            "url": "should-ignore",
        },
    )

    worksheet.batch_update.assert_called_once()
    updates = worksheet.batch_update.call_args.args[0]
    ranges = {item["range"]: item["values"][0][0] for item in updates}
    assert ranges["D2"] == CRAWL_STATUS_FINISHED
    assert ranges["E2"] == "Engineer"  # job_title
    assert ranges["H2"] == "Acme"  # job_company
    assert "unknown_field" not in str(updates)
    assert "should-ignore" not in str(updates)
    assert worksheet.batch_update.call_args.kwargs.get("raw") is False


def test_update_result_missing_raises(tmp_path: Path) -> None:
    sheets, worksheet = _make_client(tmp_path, col_job_ids=["job_id"])
    worksheet.col_values.return_value = ["job_id"]

    with pytest.raises(JobNotFoundError):
        sheets.update_result("nope", CRAWL_STATUS_FAILED, {})


def test_list_incomplete_jobs(tmp_path: Path) -> None:
    records = [
        {"job_id": "a", "crawl_status": CRAWL_STATUS_PENDING, "url": "u1"},
        {"job_id": "b", "crawl_status": CRAWL_STATUS_RUNNING, "url": "u2"},
        {"job_id": "c", "crawl_status": CRAWL_STATUS_FINISHED, "url": "u3"},
        {"job_id": "d", "crawl_status": CRAWL_STATUS_REJECTED, "url": "u4"},
        {"job_id": "e", "crawl_status": CRAWL_STATUS_FAILED, "url": "u5"},
    ]
    sheets, worksheet = _make_client(tmp_path, records=records)
    worksheet.get_all_records.return_value = records

    result = sheets.list_incomplete_jobs()

    assert [row["job_id"] for row in result] == ["a", "b"]
