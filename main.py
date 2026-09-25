"""CLI entry point and narrow compatibility wrappers for older imports."""

from __future__ import annotations

import asyncio

from telethon import TelegramClient

from couplebot.app import run
from couplebot.config import AppConfig
from couplebot.integrations.telegram.archive import (
    delete_archived_snapshot as _delete_archived_snapshot,
)
from couplebot.integrations.telegram.archive import sync_conversation


client = None


async def export_telegram_format(partner, archive):
    """Compatibility wrapper; new code calls ``sync_conversation`` directly."""
    if client is None:
        raise RuntimeError("Telegram client is not initialized")
    return await sync_conversation(client, partner, archive)


async def delete_archived_snapshot(
    telegram_client, partner, archive, reason, message_ids, dry_run
):
    """Compatibility wrapper for the previous public function."""
    return await _delete_archived_snapshot(
        telegram_client, partner, archive, reason, message_ids, dry_run
    )


async def monitor_and_clean() -> None:
    config = AppConfig.from_env()
    global client
    if client is None:
        client = TelegramClient(
            config.telegram_session, config.api_id, config.api_hash
        )
    await run(config, client)


if __name__ == "__main__":
    asyncio.run(monitor_and_clean())
