"""Start the Telegram automation process."""

from __future__ import annotations

import asyncio

from telethon import TelegramClient

from couplebot.app import run
from couplebot.config import AppConfig


async def monitor_and_clean() -> None:
    config = AppConfig.from_env()
    client = TelegramClient(config.telegram_session, config.api_id, config.api_hash)
    await run(config, client)


def main() -> None:
    asyncio.run(monitor_and_clean())


if __name__ == "__main__":
    main()
