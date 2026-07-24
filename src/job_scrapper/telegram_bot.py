"""Telegram listener: polls for updates, validates URLs, replies, and enqueues jobs.

Uses only the low-level ``telegram.Bot`` class (``get_updates``,
``send_message``, etc.) from ``python-telegram-bot`` — explicitly NOT the
``Application``/``ApplicationBuilder`` polling/handler framework. We drive
our own asyncio loop and our own offset/state persistence; PTB is used
purely for typed API calls and its built-in flood-control retry handling.

Known limitation: ``get_updates`` only returns unacknowledged updates
(Telegram buffers roughly the last 24h). It cannot fetch arbitrary chat
history. This means state-file loss beyond that window is unrecoverable via
this API — reconciliation (see ``main.py`` / ``sheets.py``) can prevent
reprocessing of already-seen updates, but it cannot recover messages that
Telegram has already dropped from its buffer.
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Bot

from job_scrapper.config import Settings
from job_scrapper.queue import Job
from job_scrapper.state import State

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    """Construct a ``telegram.Bot`` client for typed Bot API calls."""
    return Bot(token=settings.telegram_bot_token)


async def run_listener(
    bot: Bot,
    settings: Settings,
    queue: asyncio.Queue[Job],
    state: State,
) -> None:
    """Long-poll for updates in the target group and drive validate/reply/enqueue.

    TODO: Implement the real loop:
      1. Call ``bot.get_updates(offset=state["last_update_id"] + 1, ...)``
         with ``settings.telegram_poll_timeout``, restricted to
         ``settings.telegram_chat_id``.
      2. For each update's message, extract candidate URL(s).
      3. Validate via ``crawler.dispatch.is_well_formed_url`` and
         ``is_supported_site``.
      4. Reply in chat: accepted or rejected (briefly stating why).
      5. If accepted: write a ``pending`` row via ``sheets.SheetsClient`` and
         put a ``Job`` on ``queue``. If rejected: write a ``rejected`` row
         for audit (never silently drop).
      6. After processing a batch of updates, update
         ``state["last_update_id"]`` and persist via
         ``job_scrapper.state.save_state`` (batched, not per message).
    """
    raise NotImplementedError("run_listener is not yet implemented")
