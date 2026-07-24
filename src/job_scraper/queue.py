"""In-memory job queue and worker-pool plumbing.

One listener task (see ``telegram_bot.py``) produces ``Job`` items onto a
single ``asyncio.Queue``. One or more worker tasks consume from it and hand
each job to ``process_job`` for crawling, sheet updates, and chat notify.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from telegram import Bot

from job_scraper.scraper.dispatch import get_parser
from job_scraper.scraper.fetch import fetch_html
from job_scraper.sheets import (
    CRAWL_STATUS_FAILED,
    CRAWL_STATUS_FINISHED,
    CRAWL_STATUS_RUNNING,
    SheetsClient,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    """A single unit of crawl work, mirroring the relevant Sheet A columns.

    ``job_id`` is the string ``f"{chat_id}_{message_id}"``. ``chat_id`` and
    ``message_id`` are kept separately for replies / Bot API calls.
    """

    job_id: str
    url: str
    chat_id: str
    message_id: int


def create_queue() -> asyncio.Queue[Job]:
    """Create the in-memory job queue shared between the listener and workers."""
    return asyncio.Queue()


async def process_job(job: Job, sheets: SheetsClient, bot: Bot) -> None:
    """Handle a single crawl job: set running, crawl, write result, notify chat.

    1. Mark the jobs row for ``job.job_id`` as ``running``.
    2. Fetch ``job.url`` and look up its parser via ``get_parser``.
    3. Parse the page into job fields; write them + ``finished``/``failed``.
    4. Send a result-summary message back to ``job.chat_id``.
    """
    sheets.update_status(job.job_id, CRAWL_STATUS_RUNNING)

    status = CRAWL_STATUS_FAILED
    fields: dict[str, Any] = {}
    try:
        parser = get_parser(job.url)
        if parser is None:
            raise RuntimeError(f"no parser registered for {job.url!r}")
        html = await fetch_html(job.url)
        fields = parser(html)
        status = CRAWL_STATUS_FINISHED
    except Exception:  # noqa: BLE001 - record failed status; do not kill worker
        logger.exception("crawl failed for job %s", job.job_id)

    sheets.update_result(job.job_id, status, fields)
    # Lazy import: telegram_bot imports Job from this module.
    from job_scraper.telegram_bot import reply_crawl_result

    await reply_crawl_result(bot, job.chat_id, status, message_id=job.message_id)


async def _worker_loop(
    worker_id: int,
    queue: asyncio.Queue[Job],
    sheets: SheetsClient,
    bot: Bot,
) -> None:
    """Continuously pull jobs off ``queue`` and process them until cancelled."""
    logger.info("worker %d started", worker_id)
    try:
        while True:
            job = await queue.get()
            try:
                await process_job(job, sheets, bot)
            except Exception:  # noqa: BLE001 - worker must not die on a bad job
                logger.exception("worker %d failed processing job %s", worker_id, job.job_id)
            finally:
                queue.task_done()
    except asyncio.CancelledError:
        logger.info("worker %d cancelled", worker_id)
        raise


def spawn_workers(
    queue: asyncio.Queue[Job],
    worker_count: int,
    sheets: SheetsClient,
    bot: Bot,
) -> list[asyncio.Task[None]]:
    """Start ``worker_count`` worker tasks consuming from ``queue``."""
    return [
        asyncio.create_task(
            _worker_loop(i, queue, sheets, bot),
            name=f"worker-{i}",
        )
        for i in range(worker_count)
    ]


async def shutdown_workers(workers: list[asyncio.Task[None]]) -> None:
    """Cancel all worker tasks and wait for them to finish."""
    for task in workers:
        task.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
