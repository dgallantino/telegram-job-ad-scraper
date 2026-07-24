"""Entrypoint: wires config, state, the job queue/workers, and the Telegram
listener together, then runs the event loop.

Startup order:
  1. Load settings and local state.
  2. Create the job queue and spawn worker tasks.
  3. Re-enqueue any Sheet A rows left ``pending``/``running`` from a previous
     crash (TODO — depends on ``sheets.py``).
  4. Start the Telegram listener (TODO — depends on ``telegram_bot.py``).
"""

from __future__ import annotations

import asyncio
import logging

from job_scrapper import queue as job_queue
from job_scrapper import state as state_module
from job_scrapper.config import ConfigError, Settings, load_settings

logger = logging.getLogger(__name__)


async def _reenqueue_incomplete_jobs(
    settings: Settings, queue: asyncio.Queue[job_queue.Job]
) -> None:
    """Re-enqueue Sheet A rows left in ``pending``/``running`` after a crash.

    TODO: Implement once ``sheets.py`` has a real client — scan Sheet A for
    rows with ``crawl_status`` in (``pending``, ``running``) and put a
    ``Job`` on ``queue`` for each before the listener starts.
    """


async def run() -> None:
    """Build all components and run until cancelled (e.g. SIGINT/SIGTERM)."""
    logging.basicConfig(level=logging.INFO)

    settings = load_settings()
    state = state_module.load_state(settings.state_file_path)

    queue = job_queue.create_queue()
    workers = job_queue.spawn_workers(queue, settings.worker_count)

    await _reenqueue_incomplete_jobs(settings, queue)

    # TODO: Start the Telegram listener from telegram_bot.py, e.g.:
    #   bot = telegram.Bot(token=settings.telegram_bot_token)
    #   await telegram_bot.run_listener(bot, settings, queue, state)
    logger.info(
        "Scaffold ready: %d worker(s) started, listener not yet implemented.",
        settings.worker_count,
    )

    try:
        await asyncio.Event().wait()  # placeholder: block until cancelled
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
