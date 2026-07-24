"""Tests for Telegram listener, URL extraction, and reply helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, MessageEntity, Update, User

from job_scraper.config import Settings
from job_scraper.queue import Job
from job_scraper.telegram_bot import (
    _MSG_ACCEPTED,
    _MSG_CRAWL_FAILED,
    _MSG_CRAWL_FINISHED,
    _MSG_HEALTH_OK,
    extract_urls,
    reply_accepted,
    reply_crawl_result,
    reply_health,
    reply_rejected,
    run_listener,
)


@dataclass
class FakeSheets:
    pending: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def append_pending_row(self, job_id: str, timestamp: str, url: str) -> None:
        self.pending.append({"job_id": job_id, "timestamp": timestamp, "url": url})

    def append_rejected_row(
        self, job_id: str, timestamp: str, url: str, reason: str
    ) -> None:
        self.rejected.append(
            {"job_id": job_id, "timestamp": timestamp, "url": url, "reason": reason}
        )


def _settings(tmp_path: Path, chat_id: str = "-100123") -> Settings:
    return Settings(
        google_service_account_key="{}",
        google_sheets_spreadsheet_id="sheet-id",
        google_sheets_sheet_name="jobs",
        telegram_bot_token="123:ABC",
        telegram_chat_id=chat_id,
        state_file_path=str(tmp_path / "state.json"),
        worker_count=1,
        telegram_poll_timeout=1,
    )


def _chat(chat_id: int = -100123) -> Chat:
    return Chat(id=chat_id, type="supergroup", title="jobs")


def _message(
    *,
    text: str | None = None,
    caption: str | None = None,
    entities: list[MessageEntity] | None = None,
    caption_entities: list[MessageEntity] | None = None,
    chat_id: int = -100123,
    message_id: int = 42,
) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=_chat(chat_id),
        from_user=User(id=1, first_name="tester", is_bot=False),
        text=text,
        entities=entities,
        caption=caption,
        caption_entities=caption_entities,
    )


def _url_entity(text: str, url: str) -> MessageEntity:
    offset = text.index(url)
    return MessageEntity(type=MessageEntity.URL, offset=offset, length=len(url))


def _text_link_entity(offset: int, length: int, url: str) -> MessageEntity:
    return MessageEntity(
        type=MessageEntity.TEXT_LINK, offset=offset, length=length, url=url
    )


def _update(update_id: int, message: Message) -> Update:
    return Update(update_id=update_id, message=message)


async def _drive_listener(
    bot: MagicMock,
    settings: Settings,
    queue: asyncio.Queue[Job],
    state: dict[str, Any],
    sheets: FakeSheets,
    *,
    wait_until: Any,
    timeout: float = 2.0,
) -> None:
    """Run listener until ``wait_until()`` is true, then cancel."""
    task = asyncio.create_task(run_listener(bot, settings, queue, state, sheets))  # type: ignore[arg-type]
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while not wait_until():
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("listener did not reach expected state in time")
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# --- extract_urls ---


def test_extract_urls_from_text_url_entity() -> None:
    url = "https://example.com/job"
    text = f"see {url} please"
    msg = _message(text=text, entities=[_url_entity(text, url)])
    assert extract_urls(msg) == [url]


def test_extract_urls_from_text_link() -> None:
    text = "click here for job"
    msg = _message(
        text=text,
        entities=[_text_link_entity(0, 10, "https://example.com/x")],
    )
    assert extract_urls(msg) == ["https://example.com/x"]


def test_extract_urls_from_caption() -> None:
    cap = "https://example.com/c"
    msg = _message(caption=cap, caption_entities=[_url_entity(cap, cap)])
    assert extract_urls(msg) == [cap]


def test_extract_urls_dedupes_preserving_order() -> None:
    url = "https://example.com/job"
    text = f"{url} and again {url}"
    first = _url_entity(text, url)
    # second occurrence
    second_offset = text.rindex(url)
    second = MessageEntity(
        type=MessageEntity.URL, offset=second_offset, length=len(url)
    )
    msg = _message(text=text, entities=[first, second])
    assert extract_urls(msg) == [url]


def test_extract_urls_empty_when_no_urls() -> None:
    msg = _message(text="hello with no links")
    assert extract_urls(msg) == []


# --- reply helpers ---


@pytest.mark.asyncio
async def test_reply_accepted_sends_hardcoded_text() -> None:
    bot = AsyncMock()
    await reply_accepted(bot, "-100123", message_id=7)
    bot.send_message.assert_awaited_once_with(
        chat_id="-100123",
        text=_MSG_ACCEPTED,
        reply_to_message_id=7,
    )


@pytest.mark.asyncio
async def test_reply_rejected_includes_reason() -> None:
    bot = AsyncMock()
    await reply_rejected(bot, "-100123", "unsupported site", message_id=8)
    bot.send_message.assert_awaited_once_with(
        chat_id="-100123",
        text="Rejected: unsupported site",
        reply_to_message_id=8,
    )


@pytest.mark.asyncio
async def test_reply_crawl_result_finished_and_failed() -> None:
    bot = AsyncMock()
    await reply_crawl_result(bot, "-100123", "finished", message_id=1)
    await reply_crawl_result(bot, "-100123", "failed", message_id=2)
    assert bot.send_message.await_args_list[0].kwargs["text"] == _MSG_CRAWL_FINISHED
    assert bot.send_message.await_args_list[1].kwargs["text"] == _MSG_CRAWL_FAILED


@pytest.mark.asyncio
async def test_reply_health_sends_ok() -> None:
    bot = AsyncMock()
    await reply_health(bot, "-100123", message_id=9)
    bot.send_message.assert_awaited_once_with(
        chat_id="-100123",
        text=_MSG_HEALTH_OK,
        reply_to_message_id=9,
    )


# --- run_listener ---


@pytest.mark.asyncio
async def test_health_command_replies_ok(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sheets = FakeSheets()
    queue: asyncio.Queue[Job] = asyncio.Queue()
    state: dict[str, Any] = {"last_update_id": None}
    msg = _message(text="/health", message_id=3)
    calls = {"n": 0}

    async def get_updates(**kwargs: Any) -> tuple[Update, ...]:
        calls["n"] += 1
        if calls["n"] == 1:
            return (_update(60, msg),)
        await asyncio.Event().wait()
        return ()

    bot = AsyncMock()
    bot.get_updates = get_updates
    bot.send_message = AsyncMock()

    await _drive_listener(
        bot,
        settings,
        queue,
        state,
        sheets,
        wait_until=lambda: bot.send_message.await_count >= 1,
    )

    assert queue.empty()
    assert sheets.pending == []
    assert sheets.rejected == []
    bot.send_message.assert_awaited_once_with(
        chat_id="-100123",
        text=_MSG_HEALTH_OK,
        reply_to_message_id=3,
    )


@pytest.mark.asyncio
async def test_wrong_chat_advances_state_without_side_effects(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    sheets = FakeSheets()
    queue: asyncio.Queue[Job] = asyncio.Queue()
    state: dict[str, Any] = {"last_update_id": None}

    url = "https://example.com/job"
    text = url
    msg = _message(text=text, entities=[_url_entity(text, url)], chat_id=-999)
    updates_call = {"n": 0}

    async def get_updates(**kwargs: Any) -> tuple[Update, ...]:
        updates_call["n"] += 1
        if updates_call["n"] == 1:
            return (_update(10, msg),)
        await asyncio.Event().wait()
        return ()

    bot = AsyncMock()
    bot.get_updates = get_updates
    bot.send_message = AsyncMock()

    await _drive_listener(
        bot,
        settings,
        queue,
        state,
        sheets,
        wait_until=lambda: state.get("last_update_id") == 10,
    )

    assert queue.empty()
    assert sheets.pending == []
    assert sheets.rejected == []
    bot.send_message.assert_not_awaited()
    assert Path(settings.state_file_path).is_file()


@pytest.mark.asyncio
async def test_no_url_message_silent_skip(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sheets = FakeSheets()
    queue: asyncio.Queue[Job] = asyncio.Queue()
    state: dict[str, Any] = {"last_update_id": None}
    msg = _message(text="just chatting")
    calls = {"n": 0}

    async def get_updates(**kwargs: Any) -> tuple[Update, ...]:
        calls["n"] += 1
        if calls["n"] == 1:
            return (_update(11, msg),)
        await asyncio.Event().wait()
        return ()

    bot = AsyncMock()
    bot.get_updates = get_updates
    bot.send_message = AsyncMock()

    await _drive_listener(
        bot,
        settings,
        queue,
        state,
        sheets,
        wait_until=lambda: state.get("last_update_id") == 11,
    )

    assert queue.empty()
    assert sheets.pending == []
    assert sheets.rejected == []
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_accepted_allowlisted_url(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sheets = FakeSheets()
    queue: asyncio.Queue[Job] = asyncio.Queue()
    state: dict[str, Any] = {"last_update_id": None}

    url = "https://example.com/job"
    text = f"apply {url}"
    msg = _message(text=text, entities=[_url_entity(text, url)], message_id=42)
    calls = {"n": 0}

    async def get_updates(**kwargs: Any) -> tuple[Update, ...]:
        calls["n"] += 1
        if calls["n"] == 1:
            return (_update(20, msg),)
        await asyncio.Event().wait()
        return ()

    bot = AsyncMock()
    bot.get_updates = get_updates
    bot.send_message = AsyncMock()

    await _drive_listener(
        bot,
        settings,
        queue,
        state,
        sheets,
        wait_until=lambda: not queue.empty() and bool(sheets.pending),
    )

    job = queue.get_nowait()
    assert job == Job(
        job_id="-100123_42",
        url=url,
        chat_id="-100123",
        message_id=42,
    )
    assert sheets.pending[0]["job_id"] == "-100123_42"
    assert sheets.pending[0]["url"] == url
    assert sheets.rejected == []
    bot.send_message.assert_awaited()
    assert bot.send_message.await_args.kwargs["text"] == _MSG_ACCEPTED


@pytest.mark.asyncio
async def test_rejected_unsupported_site(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sheets = FakeSheets()
    queue: asyncio.Queue[Job] = asyncio.Queue()
    state: dict[str, Any] = {"last_update_id": None}

    url = "https://not-allowlisted.example/job"
    text = url
    msg = _message(text=text, entities=[_url_entity(text, url)], message_id=5)
    calls = {"n": 0}

    async def get_updates(**kwargs: Any) -> tuple[Update, ...]:
        calls["n"] += 1
        if calls["n"] == 1:
            return (_update(30, msg),)
        await asyncio.Event().wait()
        return ()

    bot = AsyncMock()
    bot.get_updates = get_updates
    bot.send_message = AsyncMock()

    await _drive_listener(
        bot,
        settings,
        queue,
        state,
        sheets,
        wait_until=lambda: bool(sheets.rejected),
    )

    assert queue.empty()
    assert sheets.pending == []
    assert sheets.rejected[0]["reason"] == "unsupported site"
    assert sheets.rejected[0]["job_id"] == "-100123_5"
    assert "Rejected: unsupported site" in bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_rejected_malformed_url(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sheets = FakeSheets()
    queue: asyncio.Queue[Job] = asyncio.Queue()
    state: dict[str, Any] = {"last_update_id": None}

    # TEXT_LINK can carry a non-http URL that fails well-formed check
    text = "click here"
    msg = _message(
        text=text,
        entities=[_text_link_entity(0, 10, "ftp://example.com/x")],
        message_id=6,
    )
    calls = {"n": 0}

    async def get_updates(**kwargs: Any) -> tuple[Update, ...]:
        calls["n"] += 1
        if calls["n"] == 1:
            return (_update(31, msg),)
        await asyncio.Event().wait()
        return ()

    bot = AsyncMock()
    bot.get_updates = get_updates
    bot.send_message = AsyncMock()

    await _drive_listener(
        bot,
        settings,
        queue,
        state,
        sheets,
        wait_until=lambda: bool(sheets.rejected),
    )

    assert queue.empty()
    assert sheets.rejected[0]["reason"] == "not a valid URL"
    assert "Rejected: not a valid URL" in bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_multi_url_unique_job_ids(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sheets = FakeSheets()
    queue: asyncio.Queue[Job] = asyncio.Queue()
    state: dict[str, Any] = {"last_update_id": None}

    u1 = "https://example.com/a"
    u2 = "https://other.example/b"
    text = f"{u1} {u2}"
    msg = _message(
        text=text,
        entities=[_url_entity(text, u1), _url_entity(text, u2)],
        message_id=99,
    )
    calls = {"n": 0}

    async def get_updates(**kwargs: Any) -> tuple[Update, ...]:
        calls["n"] += 1
        if calls["n"] == 1:
            return (_update(40, msg),)
        await asyncio.Event().wait()
        return ()

    bot = AsyncMock()
    bot.get_updates = get_updates
    bot.send_message = AsyncMock()

    await _drive_listener(
        bot,
        settings,
        queue,
        state,
        sheets,
        wait_until=lambda: queue.qsize() == 1 and len(sheets.rejected) == 1,
    )

    job = queue.get_nowait()
    assert job.job_id == "-100123_99_0"
    assert job.url == u1
    assert sheets.rejected[0]["job_id"] == "-100123_99_1"
    assert sheets.rejected[0]["url"] == u2


@pytest.mark.asyncio
async def test_offset_uses_last_update_id_plus_one(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sheets = FakeSheets()
    queue: asyncio.Queue[Job] = asyncio.Queue()
    state: dict[str, Any] = {"last_update_id": 50}
    seen_offsets: list[int | None] = []

    async def get_updates(**kwargs: Any) -> tuple[Update, ...]:
        seen_offsets.append(kwargs.get("offset"))
        await asyncio.Event().wait()
        return ()

    bot = AsyncMock()
    bot.get_updates = get_updates

    await _drive_listener(
        bot,
        settings,
        queue,
        state,
        sheets,
        wait_until=lambda: len(seen_offsets) >= 1,
    )

    assert seen_offsets[0] == 51
