import asyncio
import tempfile
import unittest
from pathlib import Path

from couplebot.features.cleanup.service import CleanupService
from couplebot.storage.archive import ArchiveError, ArchiveStore


class FakeConversation:
    latest_incoming = 10
    latest_message = 10
    read = True

    async def latest_incoming_id(self):
        return self.latest_incoming

    async def latest_message_id(self):
        return self.latest_message

    async def incoming_is_read(self, message_id):
        return self.read and message_id == self.latest_incoming

    async def unread_outgoing(self, limit, scan_limit):
        return [], 0


class CleanupServiceTests(unittest.TestCase):
    def test_new_message_during_sync_cancels_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = ArchiveStore(Path(temporary), 42, "Friend")
            conversation = FakeConversation()
            deleted = []

            async def sync():
                conversation.latest_message = 11
                return archive.export_path, [10]

            async def delete(reason, ids):
                deleted.append(ids)

            service = CleanupService(archive, conversation, sync, delete, asyncio.Lock())

            async def scenario():
                service.on_incoming(10)
                await service.on_inbox_read(10)
                service.deadline = 0
                await service.maybe_delete_after_grace_period("test")

            asyncio.run(scenario())
            self.assertEqual(deleted, [])
            self.assertEqual(archive.connection.execute("SELECT status FROM deletion_log").fetchone()[0], "cancelled")
            archive.close()

    def test_archive_failure_leaves_deletion_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = ArchiveStore(Path(temporary), 42, "Friend")
            deleted = []

            async def sync():
                raise ArchiveError("archive failed")

            async def delete(reason, ids):
                deleted.append(ids)

            service = CleanupService(archive, FakeConversation(), sync, delete, asyncio.Lock())

            async def scenario():
                service.on_incoming(10)
                await service.on_inbox_read(10)
                service.deadline = 0
                with self.assertRaises(ArchiveError):
                    await service.maybe_delete_after_grace_period("test")

            asyncio.run(scenario())
            self.assertEqual(deleted, [])
            self.assertEqual(service.pending_id, 10)
            archive.close()


if __name__ == "__main__":
    unittest.main()
