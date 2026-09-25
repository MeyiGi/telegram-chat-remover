"""Create an interactive Telegram session."""

from __future__ import annotations

import asyncio

from telethon import TelegramClient

from couplebot.config import AuthConfig
from couplebot.integrations.telegram.auth import authorize


def main() -> None:
    config = AuthConfig.from_env()
    client = TelegramClient(config.telegram_session, config.api_id, config.api_hash)
    asyncio.run(authorize(client, config.my_phone))


if __name__ == "__main__":
    main()
