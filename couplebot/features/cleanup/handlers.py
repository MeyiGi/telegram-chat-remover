"""Bind Telegram events to the cleanup state machine."""

from telethon import events
from telethon.tl.types import UserStatusOnline

from couplebot.features.cleanup.service import CleanupService


def register_cleanup_handlers(client, partner, cleanup: CleanupService) -> None:
    @client.on(events.NewMessage(incoming=True, chats=partner))
    async def incoming_handler(event):
        cleanup.on_incoming(event.message.id)

    @client.on(events.MessageRead(chats=partner, inbox=True))
    async def inbox_read_handler(event):
        await cleanup.on_inbox_read(event.max_id)

    @client.on(events.MessageRead(chats=partner))
    async def outbox_read_handler(event):
        if getattr(event, "outbox", False):
            print("Она открыла чат. Таймер удаления это не сбрасывает.")

    @client.on(events.UserUpdate(partner))
    async def user_update_handler(event):
        if getattr(event, "cancel", False):
            cleanup.on_typing_cancel()
        if getattr(event, "typing", False):
            await cleanup.on_typing()
        if isinstance(getattr(event, "status", None), UserStatusOnline):
            cleanup.on_partner_online()
