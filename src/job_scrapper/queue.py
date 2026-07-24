"""In-memory job queue and worker-pool plumbing.

One listener task (see ``telegram_bot.py``) produces ``Job`` items onto a
single ``asyncio.Queue``. One or more worker tasks consume from it and hand
each job to ``process_job`` for crawling. The queue/worker plumbing here is
real; what a worker actually does with a job (``process_job``) is still a
stub pending the crawler and Sheets implementations.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    """A single unit of crawl work, mirroring the relevant Sheet A columns."""

    job_id: str
    url: str
    chat_id: str
    message_id: int


def create_queue() -> asyncio.Queue[Job]:
    """Create the in-memory job queue shared between the listener and workers."""
    return asyncio.Queue()


async def process_job(job: Job) -> None:
    """Handle a single crawl job: set running, crawl, write result, notify chat.

    TODO: Implement once ``sheets.py`` and the real crawler dispatch/parsers
    are ready:
      1. Mark the Sheet A row for ``job.job_id`` as ``running``.
      2. Fetch ``job.url`` (httpx) and look up its parser via
         ``crawler.dispatch.get_parser``.
      3. Parse the page into job fields; write them + ``finished``/``failed``
         to Sheet A.
      4. Send a result-summary message back to ``job.chat_id``.
    """
    raise NotImplementedError("process_job is not yet implemented")


async def _worker_loop(worker_id: int, queue: asyncio.Queue[Job]) -> None:
    """Continuously pull jobs off ``queue`` and process them until cancelled."""
    logger.info("worker %d started", worker_id)
    try:
        while True:
            job = await queue.get()
            try:
                await process_job(job)
            except Exception:  # noqa: BLE001 - worker must not die on a bad job
                logger.exception("worker %d failed processing job %s", worker_id, job.job_id)
            finally:
                queue.task_done()
    except asyncio.CancelledError:
        logger.info("worker %d cancelled", worker_id)
        raise


def spawn_workers(queue: asyncio.Queue[Job], worker_count: int) -> list[asyncio.Task[None]]:
    """Start ``worker_count`` worker tasks consuming from ``queue``."""
    return [
        asyncio.create_task(_worker_loop(i, queue), name=f"worker-{i}")
        for i in range(worker_count)
    ]


async def shutdown_workers(workers: list[asyncio.Task[None]]) -> None:
    """Cancel all worker tasks and wait for them to finish."""
    for task in workers:
        task.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
