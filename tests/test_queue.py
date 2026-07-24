"""Tests for queue process_job crawl / sheet / notify flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from job_scraper.queue import Job, process_job
from job_scraper.sheets import (
    CRAWL_STATUS_FAILED,
    CRAWL_STATUS_FINISHED,
    CRAWL_STATUS_RUNNING,
)


def _job() -> Job:
    return Job(
        job_id="-100123_1",
        url="https://id.jobstreet.com/job/123",
        chat_id="-100123",
        message_id=1,
    )


def _sheets() -> MagicMock:
    return MagicMock()


@pytest.mark.asyncio
async def test_process_job_finished() -> None:
    job = _job()
    sheets = _sheets()
    on_finish = AsyncMock()
    fields = {
        "job_title": "Engineer",
        "job_description": "Build things",
        "job_location": "Jakarta",
        "job_company": "Acme",
        "job_salary": None,
        "job_type": "Full time",
        "job_posted_date": "2026-01-01",
    }
    parser = MagicMock(return_value=fields)

    with (
        patch("job_scraper.queue.get_parser", return_value=parser) as get_parser,
        patch(
            "job_scraper.queue.fetch_html",
            new_callable=AsyncMock,
            return_value="<html/>",
        ) as fetch,
    ):
        await process_job(job, sheets, on_finish)

    sheets.update_status.assert_called_once_with(job.job_id, CRAWL_STATUS_RUNNING)
    get_parser.assert_called_once_with(job.url)
    fetch.assert_awaited_once_with(job.url)
    parser.assert_called_once_with("<html/>")
    sheets.update_result.assert_called_once_with(
        job.job_id, CRAWL_STATUS_FINISHED, fields
    )
    on_finish.assert_awaited_once_with(job, CRAWL_STATUS_FINISHED)


@pytest.mark.asyncio
async def test_process_job_fetch_failure() -> None:
    job = _job()
    sheets = _sheets()
    on_finish = AsyncMock()
    request = httpx.Request("GET", job.url)
    response = httpx.Response(500, request=request)

    with (
        patch("job_scraper.queue.get_parser", return_value=MagicMock()),
        patch(
            "job_scraper.queue.fetch_html",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "server error", request=request, response=response
            ),
        ),
    ):
        await process_job(job, sheets, on_finish)

    sheets.update_status.assert_called_once_with(job.job_id, CRAWL_STATUS_RUNNING)
    sheets.update_result.assert_called_once_with(job.job_id, CRAWL_STATUS_FAILED, {})
    on_finish.assert_awaited_once_with(job, CRAWL_STATUS_FAILED)


@pytest.mark.asyncio
async def test_process_job_no_parser() -> None:
    job = _job()
    sheets = _sheets()
    on_finish = AsyncMock()

    with (
        patch("job_scraper.queue.get_parser", return_value=None),
        patch(
            "job_scraper.queue.fetch_html",
            new_callable=AsyncMock,
        ) as fetch,
    ):
        await process_job(job, sheets, on_finish)

    fetch.assert_not_awaited()
    sheets.update_status.assert_called_once_with(job.job_id, CRAWL_STATUS_RUNNING)
    sheets.update_result.assert_called_once_with(job.job_id, CRAWL_STATUS_FAILED, {})
    on_finish.assert_awaited_once_with(job, CRAWL_STATUS_FAILED)
