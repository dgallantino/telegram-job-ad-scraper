"""Entrypoint: wires config, state, the job queue/workers, and the Telegram
listener together, then runs the event loop.

Startup order:
  1. Load settings and local state.
  2. Create the job queue and spawn worker tasks.
  3. Re-enqueue any ``jobs`` rows left ``pending``/``running`` from a previous
     crash.
  4. Start the Telegram listener.
"""

from __future__ import annotations

import asyncio
import logging

from job_scraper import queue as job_queue
from job_scraper import telegram_bot
from job_scraper.config import ConfigError, load_settings
from job_scraper.sheets import SheetsClient
from job_scraper.state import StateStore

logger = logging.getLogger(__name__)


async def _reenqueue_incomplete_jobs(
    sheets: SheetsClient, queue: asyncio.Queue[job_queue.Job]
) -> None:
    """Re-enqueue ``jobs`` rows left in ``pending``/``running`` after a crash.

    Scans the worksheet via ``sheets.list_incomplete_jobs`` and puts a ``Job``
    on ``queue`` for each valid row before the listener starts. Malformed rows
    (missing ``job_id``/``url``, or unparseable ``job_id``) are skipped with a
    warning. Sheet status is left as-is; workers set ``running`` when they
    pick up each job.
    """
    rows = sheets.list_incomplete_jobs()
    enqueued = 0
    skipped = 0

    for row in rows:
        job_id = str(row.get("job_id") or "").strip()
        url = str(row.get("url") or "").strip()
        if not job_id or not url:
            skipped += 1
            logger.warning(
                "skipping incomplete row missing job_id/url: job_id=%r url=%r",
                job_id,
                url,
            )
            continue

        try:
            chat_id, message_id = telegram_bot.parse_job_id(job_id)
        except ValueError:
            skipped += 1
            logger.warning("skipping incomplete row with unparseable job_id=%r", job_id)
            continue

        await queue.put(
            job_queue.Job(
                job_id=job_id,
                url=url,
                chat_id=chat_id,
                message_id=message_id,
            )
        )
        enqueued += 1

    logger.info(
        "re-enqueued %d incomplete job(s) (%d skipped)",
        enqueued,
        skipped,
    )


async def run() -> None:
    """Build all components and run until cancelled (e.g. SIGINT/SIGTERM)."""
    logging.basicConfig(level=logging.INFO)
    # PTB uses httpx; its INFO request lines include the bot token in the URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    settings = load_settings()
    state = StateStore(settings.state_file_path).load()

    bot = telegram_bot.create_bot(settings)
    sheets = SheetsClient(settings)

    async def on_finish(job: job_queue.Job, status: str) -> None:
        await telegram_bot.on_crawl_finish(bot, job, status)

    queue = job_queue.create_queue()
    workers = job_queue.spawn_workers(queue, settings.worker_count, sheets, on_finish)

    await _reenqueue_incomplete_jobs(sheets, queue)
    logger.info("starting Telegram listener with %d worker(s)", settings.worker_count)

    try:
        await telegram_bot.run_listener(bot, settings, queue, state, sheets)
    finally:
        await job_queue.shutdown_workers(workers)


def main() -> None:
    """Synchronous console-script entrypoint."""
    try:
        asyncio.run(run())
    except ConfigError as exc:
        logging.getLogger(__name__).error("Configuration error: %s", exc)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
