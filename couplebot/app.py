"""Application startup and wiring of independent automations."""

from __future__ import annotations

import asyncio

from telethon.tl.types import UserStatusOnline

from couplebot.config import AppConfig
from couplebot.features.cleanup.handlers import register_cleanup_handlers
from couplebot.features.cleanup.service import CleanupService
from couplebot.features.diary.service import DailyDiaryService, daily_diary_loop
from couplebot.features.media_backup.service import MediaBackupService
from couplebot.features.stats.handlers import register_stats_handler
from couplebot.integrations.groq import GroqDiaryWriter
from couplebot.integrations.google_drive import GoogleDriveMediaWriter
from couplebot.integrations.notion import NotionDiaryWriter
from couplebot.integrations.telegram.archive import (
    delete_archived_snapshot,
    sync_conversation,
)
from couplebot.integrations.telegram.conversation import TelegramConversation
from couplebot.storage.archive import ArchiveStore


async def _find_partner(client, username_or_phone: str):
    normalized = username_or_phone.lstrip("+@").lower()
    if not normalized.isdigit() and hasattr(client, "get_entity"):
        try:
            return await client.get_entity(username_or_phone)
        except ValueError:
            pass
    async for dialog in client.iter_dialogs():
        phone = getattr(dialog.entity, "phone", None)
        username = getattr(dialog.entity, "username", None)
        if (phone and phone == normalized) or (
            username and username.lower() == normalized
        ):
            return dialog.entity
    raise ValueError(f"Не найден контакт {username_or_phone} в диалогах")


async def run(config: AppConfig, client) -> None:
    await client.start(
        phone=config.my_phone,
        code_callback=lambda: input("Введи код из Telegram: "),
        password=lambda: input("Введи пароль 2FA: "),
    )
    print("Мониторинг запущен...")
    partner = await _find_partner(client, config.girlfriend_username)
    drive_writer = None
    if config.google_drive_enabled:
        drive_writer = GoogleDriveMediaWriter.from_token_file(
            config.google_drive_token_file, config.google_drive_folder_name
        )
    archive = ArchiveStore(
        config.data_dir, partner.id, partner.first_name or config.girlfriend_username
    )
    media_backup = None
    if drive_writer is not None:
        media_backup = MediaBackupService(archive, drive_writer)
        print(f"Резервная копия медиа в Google Drive включена: {config.google_drive_folder_name}.")
    sync_lock = asyncio.Lock()
    conversation = TelegramConversation(client, partner)
    tasks: list[asyncio.Task] = []

    async def sync_archive():
        result = await sync_conversation(client, partner, archive)
        if media_backup is not None:
            uploaded = await media_backup.upload_pending()
            if uploaded:
                print(f"В Google Drive загружено файлов: {uploaded}.")
        return result

    async def delete_snapshot(reason: str, message_ids: list[int]) -> None:
        await delete_archived_snapshot(
            client, partner, archive, reason, message_ids, config.delete_dry_run
        )

    cleanup = CleanupService(
        archive,
        conversation,
        sync_archive,
        delete_snapshot,
        sync_lock,
        grace_period_seconds=config.delete_grace_period_seconds,
        recheck_seconds=config.background_recheck_interval_seconds,
        typing_unread_limit=config.typing_unread_messages_limit,
        outgoing_scan_limit=config.outgoing_read_scan_limit,
    )

    try:
        if media_backup is not None:
            uploaded = await media_backup.upload_pending()
            if uploaded:
                print(f"В Google Drive загружено файлов из старого архива: {uploaded}.")
        await cleanup.restore(
            isinstance(getattr(partner, "status", None), UserStatusOnline)
        )

        if config.diary_enabled and config.groq_api_key and config.notion_token and (
            config.notion_diary_parent_page_id or config.notion_diary_data_source_id
        ):
            groq_writer = GroqDiaryWriter(config.groq_api_key, model=config.groq_model)
            notion_writer = NotionDiaryWriter(
                config.notion_token,
                parent_page_id=config.notion_diary_parent_page_id or None,
                data_source_id=config.notion_diary_data_source_id or None,
                title_property=config.notion_diary_title_property,
            )

            async def sync_diary_archive():
                async with sync_lock:
                    await sync_archive()

            diary = DailyDiaryService(
                archive,
                groq_writer,
                notion_writer,
                config.diary_timezone,
                sync_callback=sync_diary_archive,
                max_messages=config.diary_max_messages,
            )
            tasks.append(
                asyncio.create_task(
                    daily_diary_loop(
                        diary, config.diary_timezone, hour=config.diary_hour
                    )
                )
            )
            print(
                f"Дневник включён: каждый день в {config.diary_hour:02d}:00 "
                f"({config.diary_timezone}) за предыдущий день."
            )
        elif config.diary_enabled:
            print(
                "Дневник отключён: нужны GROQ_API_KEY, NOTION_TOKEN "
                "и NOTION_DIARY_PARENT_PAGE_ID или NOTION_DIARY_DATA_SOURCE_ID."
            )

        register_cleanup_handlers(client, partner, cleanup)
        register_stats_handler(
            client,
            partner,
            archive.export_path,
            config.chat_display_name,
            config.my_export_name,
            sync_lock,
            sync_archive,
        )

        tasks.append(asyncio.create_task(cleanup.run_recheck_loop()))
        await client.run_until_disconnected()
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        archive.close()
