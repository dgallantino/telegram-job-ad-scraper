"""Tests for startup re-enqueue of incomplete jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from job_scraper.main import _reenqueue_incomplete_jobs
from job_scraper.queue import Job


@dataclass
class FakeSheets:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def list_incomplete_jobs(self) -> list[dict[str, Any]]:
        return list(self.rows)


async def _drain(queue: asyncio.Queue[Job]) -> list[Job]:
    jobs: list[Job] = []
    while not queue.empty():
        jobs.append(queue.get_nowait())
    return jobs


@pytest.mark.asyncio
async def test_reenqueue_pending_and_running() -> None:
    sheets = FakeSheets(
        rows=[
            {
                "job_id": "-100123_42",
                "url": "https://example.com/a",
                "crawl_status": "pending",
            },
            {
                "job_id": "-100123_43_1",
                "url": "https://example.com/b",
                "crawl_status": "running",
            },
        ]
    )
    queue: asyncio.Queue[Job] = asyncio.Queue()

    await _reenqueue_incomplete_jobs(sheets, queue)

    jobs = await _drain(queue)
    assert jobs == [
        Job(
            job_id="-100123_42",
            url="https://example.com/a",
            chat_id="-100123",
            message_id=42,
        ),
        Job(
            job_id="-100123_43_1",
            url="https://example.com/b",
            chat_id="-100123",
            message_id=43,
        ),
    ]


@pytest.mark.asyncio
async def test_reenqueue_skips_malformed_rows() -> None:
    sheets = FakeSheets(
        rows=[
            {"job_id": "", "url": "https://example.com/a"},
            {"job_id": "-100123_42", "url": ""},
            {"job_id": "not-a-job-id", "url": "https://example.com/b"},
            {
                "job_id": "-100123_99",
                "url": "https://example.com/ok",
            },
        ]
    )
    queue: asyncio.Queue[Job] = asyncio.Queue()

    await _reenqueue_incomplete_jobs(sheets, queue)

    jobs = await _drain(queue)
    assert jobs == [
        Job(
            job_id="-100123_99",
            url="https://example.com/ok",
            chat_id="-100123",
            message_id=99,
        )
    ]


@pytest.mark.asyncio
async def test_reenqueue_empty() -> None:
    sheets = FakeSheets(rows=[])
    queue: asyncio.Queue[Job] = asyncio.Queue()

    await _reenqueue_incomplete_jobs(sheets, queue)

    assert queue.empty()
