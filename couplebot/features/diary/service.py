"""Daily diary workflow and Telegram transcript formatting."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from couplebot.storage.archive import ArchiveStore
from couplebot.integrations.groq import GroqDiaryWriter
from couplebot.integrations.notion import DiaryError, NotionDiaryWriter


def _message_text(message: dict) -> str:
    text = message.get("text", "")
    if isinstance(text, list):
        text = "".join(
            part if isinstance(part, str) else str(part.get("text", ""))
            for part in text
        )
    text = str(text or "").strip()
    if text:
        return text
    media_type = message.get("media_type")
    if message.get("photo"):
        return "[фото]"
    return f"[{media_type}]" if media_type else "[сообщение без текста]"


def build_transcript(
    messages: list[dict],
    timezone_name: str,
    max_messages: int = 500,
    max_transcript_chars: int = 30000,
) -> str:
    """Format archived messages for diary generation, with bounded size."""
    local_timezone = ZoneInfo(timezone_name)
    selected = messages[:max_messages]
    lines = []
    for message in selected:
        raw_date = message.get("date")
        try:
            parsed = datetime.fromisoformat(raw_date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            timestamp = parsed.astimezone(local_timezone).strftime("%H:%M")
        except (TypeError, ValueError):
            timestamp = "??:??"
        sender = message.get("from") or message.get("actor") or "Собеседник"
        lines.append(f"[{timestamp}] {sender}: {_message_text(message)}")
    result = "\n".join(lines)
    if len(messages) > len(selected):
        result += f"\n[Ещё сообщений не показано: {len(messages) - len(selected)}]"
    if len(result) > max_transcript_chars:
        result = result[:max_transcript_chars] + "\n[Текст обрезан]"
    return result or "[За этот день сообщений в архиве нет]"


class DailyDiaryService:
    def __init__(
        self,
        archive: ArchiveStore,
        groq_writer: GroqDiaryWriter,
        notion_writer: NotionDiaryWriter,
        timezone_name: str,
        sync_callback: Callable[[], Awaitable[object]] | None = None,
        max_messages: int = 500,
        max_transcript_chars: int = 30000,
    ):
        self.archive = archive
        self.groq_writer = groq_writer
        self.notion_writer = notion_writer
        self.timezone_name = timezone_name
        self.timezone = ZoneInfo(timezone_name)
        self.sync_callback = sync_callback
        self.max_messages = max_messages
        self.max_transcript_chars = max_transcript_chars

    def _transcript(self, messages: list[dict]) -> str:
        return build_transcript(
            messages,
            self.timezone_name,
            self.max_messages,
            self.max_transcript_chars,
        )

    async def create_for_date(self, diary_date: date) -> str | None:
        if self.archive.diary_status(diary_date) == "completed":
            return None
        self.archive.record_diary_run(diary_date, "running")
        try:
            if self.sync_callback:
                await self.sync_callback()
            messages = self.archive.messages_for_day(diary_date, self.timezone_name)
            transcript = self._transcript(messages)
            markdown = await self.groq_writer.write(diary_date, transcript)
            page_id = await self.notion_writer.create(diary_date, markdown, len(messages))
            self.archive.record_diary_run(diary_date, "completed", page_id)
            return page_id
        except Exception as exc:
            self.archive.record_diary_run(diary_date, "failed", detail=str(exc)[:1000])
            raise


async def daily_diary_loop(
    service: DailyDiaryService,
    timezone_name: str,
    hour: int = 5,
    retry_seconds: int = 900,
) -> None:
    local_timezone = ZoneInfo(timezone_name)
    while True:
        now = datetime.now(timezone.utc).astimezone(local_timezone)
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now < scheduled:
            await asyncio.sleep(max(1, (scheduled - now).total_seconds()))
            continue

        due_date = now.date() - timedelta(days=1)
        diary_date = service.archive.next_diary_date(due_date)
        if diary_date is None:
            next_scheduled = scheduled + timedelta(days=1)
            await asyncio.sleep(
                max(1, (next_scheduled - datetime.now(timezone.utc).astimezone(local_timezone)).total_seconds())
            )
            continue
        try:
            page_id = await service.create_for_date(diary_date)
            if page_id:
                print(f"Дневник за {diary_date} записан в Notion.")
        except Exception as exc:
            print(f"Дневник за {diary_date} не записан: {exc}. Повтор через 15 минут.")
            await asyncio.sleep(retry_seconds)
            continue


__all__ = ["DailyDiaryService", "DiaryError", "_message_text", "build_transcript", "daily_diary_loop"]
