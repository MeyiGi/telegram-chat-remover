"""Read-only Telegram operations used by conversation features."""

from __future__ import annotations

from telethon.tl.functions.messages import GetPeerDialogsRequest
from telethon.tl.types import InputDialogPeer


class TelegramConversation:
    def __init__(self, client, partner):
        self.client = client
        self.partner = partner

    async def latest_incoming_id(self) -> int | None:
        async for message in self.client.iter_messages(self.partner):
            if not message.out:
                return message.id
        return None

    async def latest_message_id(self) -> int | None:
        messages = await self.client.get_messages(self.partner, limit=1)
        return messages[0].id if messages else None

    async def _dialog(self):
        response = await self.client(
            GetPeerDialogsRequest(peers=[InputDialogPeer(peer=self.partner)])
        )
        return response.dialogs[0] if response.dialogs else None

    async def incoming_is_read(self, message_id: int | None) -> bool:
        if not message_id:
            return False
        dialog = await self._dialog()
        return bool(dialog and dialog.read_inbox_max_id >= message_id)

    async def unread_outgoing(
        self, limit: int, scan_limit: int
    ) -> tuple[list, int]:
        dialog = await self._dialog()
        if dialog is None:
            return [], 0
        read_max = getattr(dialog, "read_outbox_max_id", 0) or 0
        unread = []
        async for message in self.client.iter_messages(self.partner, limit=scan_limit):
            if not getattr(message, "out", False):
                continue
            if message.id <= read_max:
                break
            unread.append(message)
            if len(unread) >= limit:
                break
        unread.reverse()
        return unread, read_max
