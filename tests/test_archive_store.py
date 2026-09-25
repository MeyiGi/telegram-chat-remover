import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from couplebot.storage.archive import ArchiveError, ArchiveStore


class ArchiveStoreTests(unittest.TestCase):
    def test_diary_due_date_retries_and_catches_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ArchiveStore(Path(temporary), 42, "Friend")
            self.assertEqual(store.next_diary_date(date(2026, 9, 24)), date(2026, 9, 24))
            store.record_diary_run(date(2026, 9, 24), "failed")
            self.assertEqual(store.next_diary_date(date(2026, 9, 25)), date(2026, 9, 24))
            store.record_diary_run(date(2026, 9, 24), "completed", "page-id")
            self.assertEqual(store.next_diary_date(date(2026, 9, 26)), date(2026, 9, 25))
            store.close()

    def test_import_export_and_restart_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            legacy = {
                "name": "Friend",
                "type": "personal_chat",
                "id": 42,
                "messages": [{"id": 1, "type": "message", "text": "old"}],
            }
            (data_dir / "chat_export.json").write_text(
                json.dumps(legacy), encoding="utf-8"
            )

            store = ArchiveStore(data_dir, 42, "Friend")
            store.save_messages([{"id": 2, "type": "message", "text": "new"}])
            store.verify_messages([1, 2])
            store.save_cleanup_state(2, 2, 12345.0)
            export_path = store.write_json_export()
            self.assertEqual(
                [message["text"] for message in json.loads(export_path.read_text())["messages"]],
                ["old", "new"],
            )
            store.close()

            reopened = ArchiveStore(data_dir, 42, "Friend")
            self.assertEqual(reopened.load_cleanup_state(), (2, 2, 12345.0))
            reopened.verify_messages([1, 2])
            reopened.close()

    def test_missing_media_prevents_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ArchiveStore(Path(temporary), 42, "Friend")
            store.save_messages(
                [{"id": 1, "type": "message", "photo": "media/42/1.jpg"}]
            )
            with self.assertRaises(ArchiveError):
                store.verify_messages([1])
            media_file = store.media_dir / "1.jpg"
            media_file.parent.mkdir(parents=True)
            media_file.write_bytes(b"image")
            store.verify_messages([1])
            store.close()

    def test_failed_export_keeps_previous_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ArchiveStore(Path(temporary), 42, "Friend")
            store.export_path.write_text("previous", encoding="utf-8")
            store.save_messages([{"id": 1, "type": "message", "text": "new"}])
            with patch("couplebot.storage.archive.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    store.write_json_export()
            self.assertEqual(store.export_path.read_text(), "previous")
            self.assertEqual(list(Path(temporary).glob(".chat_export-*")), [])
            store.close()


if __name__ == "__main__":
    unittest.main()
