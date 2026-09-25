"""Upload archived media once and persist successful Drive IDs locally."""

from __future__ import annotations

import asyncio

from couplebot.storage.archive import ArchiveStore


class MediaBackupService:
    def __init__(self, archive: ArchiveStore, drive_writer):
        self.archive = archive
        self.drive_writer = drive_writer
        self._lock = asyncio.Lock()

    async def upload_pending(self) -> int:
        """Upload media from current and historical local archive records."""
        uploaded_count = 0
        async with self._lock:
            for relative_path, path in self.archive.pending_drive_media():
                file_id = await asyncio.to_thread(
                    self.drive_writer.upload_media, path, relative_path
                )
                self.archive.mark_drive_media_uploaded(relative_path, file_id)
                uploaded_count += 1
        return uploaded_count
