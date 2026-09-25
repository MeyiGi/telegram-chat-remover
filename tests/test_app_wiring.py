import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from couplebot.app import _find_partner, run
from couplebot.config import AppConfig, AuthConfig


class FakeClient:
    def __init__(self):
        self.started = False
        self.waited = False
        self.handlers = []

    async def start(self, **kwargs):
        self.started = True

    async def iter_dialogs(self):
        partner = SimpleNamespace(
            id=42, first_name="Friend", username="test_contact", phone=None, status=None
        )
        yield SimpleNamespace(entity=partner)

    def on(self, event):
        def register(handler):
            self.handlers.append(handler)
            return handler
        return register

    async def run_until_disconnected(self):
        self.waited = True


class AppWiringTests(unittest.TestCase):
    def test_auth_configuration_does_not_require_contact(self):
        with patch.dict(
            "os.environ",
            {
                "API_ID": "12345",
                "API_HASH": "test-hash",
                "MY_PHONE": "+10000000000",
                "GIRLFRIEND_USERNAME": "",
            },
        ):
            self.assertEqual(AuthConfig.from_env().api_id, 12345)

    def test_username_can_be_resolved_without_existing_dialog(self):
        class LookupClient:
            async def get_entity(self, username):
                return SimpleNamespace(id=42, username=username)

            async def iter_dialogs(self):
                raise AssertionError("A resolved username should not need a dialog")
                yield

        partner = asyncio.run(_find_partner(LookupClient(), "@test_contact"))
        self.assertEqual(partner.id, 42)

    def test_start_registers_features_and_closes_storage(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            "os.environ",
            {
                "API_ID": "12345",
                "API_HASH": "test-hash",
                "MY_PHONE": "+10000000000",
                "GIRLFRIEND_USERNAME": "test_contact",
                "GOOGLE_DRIVE_ENABLED": "0",
                "DIARY_ENABLED": "0",
                "DATA_DIR": temporary,
            },
        ):
            config = AppConfig.from_env()
            client = FakeClient()
            asyncio.run(run(config, client))
            self.assertTrue(client.started)
            self.assertTrue(client.waited)
            self.assertEqual(len(client.handlers), 5)
            self.assertTrue((Path(temporary) / "archive.sqlite3").is_file())


if __name__ == "__main__":
    unittest.main()
