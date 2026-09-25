import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from couplebot.integrations.telegram.archive import (
    delete_archived_snapshot,
    sync_conversation,
)
from couplebot.storage.archive import ArchiveStore


class FakeMessage:
    def __init__(self, message_id, *, media=False):
        self.id = message_id
        self.date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.text = "hello"
        self.entities = None
        self.sender_id = 10
        self.reply_to_msg_id = None
        self.edit_date = None
        self.photo = object() if media else None
        self.file = SimpleNamespace(ext=".jpg") if media else None
        self.media = self.photo
        self.sticker = None
        self.voice = None
        self.video = None

    async def get_sender(self):
        return SimpleNamespace(id=10, first_name="Friend", last_name="")


class FakeClient:
    def __init__(self, messages, *, fail_download=False, leave_messages=False):
        self.messages = messages
        self.fail_download = fail_download
        self.leave_messages = leave_messages
        self.deleted = []

    async def iter_messages(self, _partner, *, reverse=False):
        for message in self.messages if reverse else reversed(self.messages):
            yield message

    async def download_media(self, _message, *, file):
        if self.fail_download:
            raise OSError("download failed")
        Path(file).write_bytes(b"photo contents")
        return file

    async def delete_messages(self, _partner, message_ids, *, revoke):
        self.deleted.append((list(message_ids), revoke))
        if not self.leave_messages:
            self.messages = [msg for msg in self.messages if msg.id not in message_ids]


class BackupFlowTests(unittest.TestCase):
    def test_media_is_saved_before_json_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = ArchiveStore(Path(temporary), 42, "Friend")
            fake = FakeClient([FakeMessage(1), FakeMessage(2, media=True)])
            export_path, live_ids = asyncio.run(
                sync_conversation(fake, SimpleNamespace(id=42), archive)
            )
            self.assertEqual(live_ids, [1, 2])
            exported = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(len(exported["messages"]), 2)
            photo = Path(temporary) / exported["messages"][1]["photo"]
            self.assertEqual(photo.read_bytes(), b"photo contents")
            archive.close()

    def test_failed_download_leaves_archive_unpublished(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = ArchiveStore(Path(temporary), 42, "Friend")
            fake = FakeClient([FakeMessage(1, media=True)], fail_download=True)
            with self.assertRaises(OSError):
                asyncio.run(sync_conversation(fake, SimpleNamespace(id=42), archive))
            self.assertFalse(archive.export_path.exists())
            self.assertEqual(
                archive.connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0
            )
            archive.close()

    def test_preview_does_not_call_telegram_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = ArchiveStore(Path(temporary), 42, "Friend")
            fake = FakeClient([FakeMessage(1)])
            asyncio.run(
                delete_archived_snapshot(fake, SimpleNamespace(id=42), archive,
                                         "test", [1], True)
            )
            self.assertEqual(fake.deleted, [])
            self.assertEqual(
                archive.connection.execute(
                    "SELECT status FROM deletion_log ORDER BY id DESC LIMIT 1"
                ).fetchone()[0],
                "preview",
            )
            archive.close()

    def test_incomplete_telegram_delete_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = ArchiveStore(Path(temporary), 42, "Friend")
            fake = FakeClient([FakeMessage(1)], leave_messages=True)
            with self.assertRaisesRegex(Exception, "remain after deletion"):
                asyncio.run(
                    delete_archived_snapshot(fake, SimpleNamespace(id=42), archive,
                                             "test", [1], False)
                )
            self.assertEqual(fake.deleted, [([1], True)])
            self.assertEqual(
                archive.connection.execute(
                    "SELECT status FROM deletion_log ORDER BY id DESC LIMIT 1"
                ).fetchone()[0],
                "failed",
            )
            archive.close()


if __name__ == "__main__":
    unittest.main()
