"""Telegram command handler for the statistics feature."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

from telethon import events

from couplebot.features.stats.report import build_statistics_from_export, chunk_text


def register_stats_handler(
    client,
    partner,
    export_path: Path,
    chat_display_name: str,
    my_export_name: str,
    sync_lock: asyncio.Lock,
    sync_archive: Callable[[], Awaitable[object]],
) -> None:
    @client.on(events.NewMessage(outgoing=True))
    async def stats_handler(event):
        chat = await event.get_chat()
        if getattr(chat, "id", None) != partner.id:
            return
        if (event.raw_text or "").strip().lower() not in {"/stats", "/statistics"}:
            return
        await event.delete()
        try:
            async with sync_lock:
                await sync_archive()
            report = build_statistics_from_export(
                export_path, chat_display_name, my_export_name
            )
            for chunk in chunk_text(report):
                await client.send_message(partner, chunk, parse_mode=None)
        except Exception as exc:
            print(f"/stats ошибка: {exc}")
            await client.send_message(
                partner, f"Не удалось собрать статистику: {exc}", parse_mode=None
            )
