"""Checks that the CLI modules delegate startup to the application."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from couplebot.cli import auth as auth_cli
from couplebot.cli import run as run_cli


class CliTests(unittest.TestCase):
    def test_run_creates_client_and_starts_app(self):
        config = SimpleNamespace(telegram_session="test", api_id=123, api_hash="hash")
        with (
            patch.object(run_cli.AppConfig, "from_env", return_value=config),
            patch.object(run_cli, "TelegramClient") as client_type,
            patch.object(run_cli, "run", new_callable=AsyncMock) as run_app,
        ):
            asyncio.run(run_cli.monitor_and_clean())

        client_type.assert_called_once_with("test", 123, "hash")
        run_app.assert_awaited_once_with(config, client_type.return_value)

    def test_auth_creates_client_and_authorizes(self):
        config = SimpleNamespace(
            telegram_session="test", api_id=123, api_hash="hash", my_phone="+1000"
        )
        with (
            patch.object(auth_cli.AuthConfig, "from_env", return_value=config),
            patch.object(auth_cli, "TelegramClient") as client_type,
            patch.object(auth_cli, "authorize", new_callable=AsyncMock) as authorize,
        ):
            auth_cli.main()

        client_type.assert_called_once_with("test", 123, "hash")
        authorize.assert_awaited_once_with(client_type.return_value, "+1000")


if __name__ == "__main__":
    unittest.main()
