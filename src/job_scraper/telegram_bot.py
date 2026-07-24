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
from datetime import datetime, timezone

from telegram import Bot, Message, MessageEntity, Update
from telegram.error import NetworkError, TelegramError, TimedOut

from job_scraper.config import Settings
from job_scraper.scraper.dispatch import is_supported_site, is_well_formed_url
from job_scraper.queue import Job
from job_scraper.sheets import SheetsClient
from job_scraper.state import StateStore

logger = logging.getLogger(__name__)

_URL_ENTITY_TYPES = [MessageEntity.URL, MessageEntity.TEXT_LINK]

_MSG_ACCEPTED = "Accepted — queued for crawl."
_MSG_CRAWL_FINISHED = "Crawl finished (stub)."
_MSG_CRAWL_FAILED = "Crawl failed (stub)."
_MSG_HEALTH_OK = "ok"

_REASON_NOT_VALID = "not a valid URL"
_REASON_UNSUPPORTED = "unsupported site"


def create_bot(settings: Settings) -> Bot:
    """Construct a ``telegram.Bot`` client for typed Bot API calls."""
    return Bot(token=settings.telegram_bot_token)


def extract_urls(message: Message) -> list[str]:
    """Return unique http(s) candidate strings from URL / TEXT_LINK entities.

    Preserves first-seen order. Looks at both message text and caption.
    For ``TEXT_LINK``, uses ``entity.url``; for ``URL``, uses the entity text.
    """
    urls: list[str] = []
    seen: set[str] = set()

    def _add(parsed: dict[MessageEntity, str]) -> None:
        for entity, value in parsed.items():
            if entity.type == MessageEntity.TEXT_LINK:
                url = entity.url or ""
            else:
                url = value
            if url and url not in seen:
                seen.add(url)
                urls.append(url)

    if message.text:
        _add(message.parse_entities(types=_URL_ENTITY_TYPES))
    if message.caption:
        _add(message.parse_caption_entities(types=_URL_ENTITY_TYPES))
    return urls


async def reply_accepted(
    bot: Bot,
    chat_id: int | str,
    *,
    message_id: int | None = None,
) -> None:
    """Send a hardcoded accept acknowledgment (optionally as a reply)."""
    await bot.send_message(
        chat_id=chat_id,
        text=_MSG_ACCEPTED,
        reply_to_message_id=message_id,
    )


async def reply_rejected(
    bot: Bot,
    chat_id: int | str,
    reason: str,
    *,
    message_id: int | None = None,
) -> None:
    """Send a reject acknowledgment including ``reason`` (optionally as a reply)."""
    await bot.send_message(
        chat_id=chat_id,
        text=f"Rejected: {reason}",
        reply_to_message_id=message_id,
    )


async def reply_crawl_result(
    bot: Bot,
    chat_id: int | str,
    status: str,
    *,
    message_id: int | None = None,
) -> None:
    """Send a hardcoded crawl-result stub for workers (finished vs failed)."""
    text = _MSG_CRAWL_FINISHED if status == "finished" else _MSG_CRAWL_FAILED
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_to_message_id=message_id,
    )


async def on_crawl_finish(bot: Bot, job: Job, status: str) -> None:
    """Queue ``on_finish`` helper: reply with crawl status for ``job``."""
    await reply_crawl_result(bot, job.chat_id, status, message_id=job.message_id)


async def reply_health(
    bot: Bot,
    chat_id: int | str,
    *,
    message_id: int | None = None,
) -> None:
    """Reply to a ``/health`` smoke-test command with a fixed ok status."""
    await bot.send_message(
        chat_id=chat_id,
        text=_MSG_HEALTH_OK,
        reply_to_message_id=message_id,
    )


def _is_health_command(message: Message) -> bool:
    """True when the message is ``/health`` or ``/health@BotName``."""
    text = (message.text or "").strip()
    if not text.startswith("/"):
        return False
    command = text.split(maxsplit=1)[0]
    command = command.split("@", 1)[0].lower()
    return command == "/health"


def _job_id(chat_id: str, message_id: int, index: int, total: int) -> str:
    if total == 1:
        return f"{chat_id}_{message_id}"
    return f"{chat_id}_{message_id}_{index}"


def parse_job_id(job_id: str) -> tuple[str, int]:
    """Parse ``{chat_id}_{message_id}`` or ``{chat_id}_{message_id}_{index}``.

    Returns ``(chat_id, message_id)``. The optional trailing index is ignored.

    Raises:
        ValueError: If ``job_id`` is empty or does not match a known format.
    """
    if not job_id:
        raise ValueError("job_id is empty")

    # Multi-URL form first so a trailing index is not treated as message_id.
    parts = job_id.rsplit("_", 2)
    if len(parts) == 3:
        chat_id, message_id_str, index_str = parts
        if chat_id and message_id_str.isdigit() and index_str.isdigit():
            message_id = int(message_id_str)
            if message_id > 0:
                return chat_id, message_id

    parts = job_id.rsplit("_", 1)
    if len(parts) != 2:
        raise ValueError(f"invalid job_id: {job_id!r}")
    chat_id, message_id_str = parts
    if not chat_id or not message_id_str.isdigit():
        raise ValueError(f"invalid job_id: {job_id!r}")
    message_id = int(message_id_str)
    if message_id <= 0:
        raise ValueError(f"invalid job_id: {job_id!r}")
    return chat_id, message_id


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _handle_message(
    bot: Bot,
    settings: Settings,
    queue: asyncio.Queue[Job],
    sheets: SheetsClient,
    message: Message,
) -> None:
    chat_id = str(message.chat.id)
    if chat_id != settings.telegram_chat_id:
        return

    logger.debug(f"message: {message}")
    if _is_health_command(message):
        await reply_health(bot, chat_id, message_id=message.message_id)
        return

    urls = extract_urls(message)
    if not urls:
        return

    message_id = message.message_id
    total = len(urls)
    timestamp = _utc_timestamp()

    for index, url in enumerate(urls):
        job_id = _job_id(chat_id, message_id, index, total)

        if not is_well_formed_url(url):
            reason = _REASON_NOT_VALID
            await reply_rejected(bot, chat_id, reason, message_id=message_id)
            sheets.append_rejected_row(job_id, timestamp, url, reason)
            continue

        if not is_supported_site(url):
            reason = _REASON_UNSUPPORTED
            await reply_rejected(bot, chat_id, reason, message_id=message_id)
            sheets.append_rejected_row(job_id, timestamp, url, reason)
            continue

        await reply_accepted(bot, chat_id, message_id=message_id)
        sheets.append_pending_row(job_id, timestamp, url)
        await queue.put(
            Job(
                job_id=job_id,
                url=url,
                chat_id=chat_id,
                message_id=message_id,
            )
        )


async def run_listener(
    bot: Bot,
    settings: Settings,
    queue: asyncio.Queue[Job],
    state: StateStore,
    sheets: SheetsClient,
) -> None:
    """Long-poll for updates in the target group and drive validate/reply/enqueue."""
    logger.info(
        "listener started for chat_id=%s poll_timeout=%s",
        settings.telegram_chat_id,
        settings.telegram_poll_timeout,
    )

    while True:
        last_update_id = state.last_update_id
        offset = None if last_update_id is None else last_update_id + 1

        try:
            updates: tuple[Update, ...] = await bot.get_updates(
                offset=offset,
                timeout=settings.telegram_poll_timeout,
                allowed_updates=["message"],
            )
        except (TimedOut, NetworkError) as exc:
            logger.warning("get_updates transient error: %s", exc)
            continue
        except TelegramError:
            logger.exception("get_updates Telegram error")
            continue

        if not updates:
            continue

        max_update_id = max(u.update_id for u in updates)

        for update in updates:
            message = update.message
            if message is None:
                continue
            try:
                await _handle_message(bot, settings, queue, sheets, message)
            except Exception:  # noqa: BLE001 - one bad message must not kill the loop
                logger.exception(
                    "failed handling update_id=%s message_id=%s",
                    update.update_id,
                    message.message_id,
                )

        state.last_update_id = max_update_id
        state.save()
