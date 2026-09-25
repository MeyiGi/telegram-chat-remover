"""Durable read-receipt based Telegram cleanup state machine."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from couplebot.storage.archive import ArchiveStore


class ConversationReader(Protocol):
    async def latest_incoming_id(self) -> int | None: ...
    async def latest_message_id(self) -> int | None: ...
    async def incoming_is_read(self, message_id: int | None) -> bool: ...
    async def unread_outgoing(self, limit: int, scan_limit: int) -> tuple[list, int]: ...


SyncArchive = Callable[[], Awaitable[tuple[Path, list[int]]]]
DeleteSnapshot = Callable[[str, list[int]], Awaitable[None]]


def _duration_label(seconds: int) -> str:
    minutes, remaining = divmod(seconds, 60)
    if minutes and not remaining:
        return f"{minutes} мин"
    return f"{seconds} сек"


class CleanupService:
    def __init__(
        self,
        archive: ArchiveStore,
        conversation: ConversationReader,
        sync_archive: SyncArchive,
        delete_snapshot: DeleteSnapshot,
        sync_lock: asyncio.Lock,
        grace_period_seconds: int = 1800,
        recheck_seconds: int = 2,
        typing_unread_limit: int = 20,
        outgoing_scan_limit: int = 100,
    ):
        self.archive = archive
        self.conversation = conversation
        self.sync_archive = sync_archive
        self.delete_snapshot = delete_snapshot
        self.sync_lock = sync_lock
        self.grace_period_seconds = grace_period_seconds
        self.recheck_seconds = recheck_seconds
        self.typing_unread_limit = typing_unread_limit
        self.outgoing_scan_limit = outgoing_scan_limit
        (
            self.last_incoming_id,
            self.pending_id,
            self.deadline,
        ) = archive.load_cleanup_state()
        self.last_typing_report_key: tuple[int, ...] | None = None

    def _persist(self) -> None:
        self.archive.save_cleanup_state(
            self.last_incoming_id, self.pending_id, self.deadline
        )

    async def restore(self, partner_online: bool) -> None:
        if self.last_incoming_id is None:
            return
        current_id = await self.conversation.latest_incoming_id()
        if current_id != self.last_incoming_id:
            self.last_incoming_id = None
            self.pending_id = None
            self.deadline = None
            self._persist()
            print("После перезапуска история изменилась; ожидание удаления сброшено.")
        elif self.deadline is not None and (
            self.deadline <= time.time() or partner_online
        ):
            self.pending_id = None
            self.deadline = None
            self._persist()
            print("Таймер истёк во время остановки или контакт онлайн; удаление отменено.")

    def on_incoming(self, message_id: int) -> None:
        self.last_incoming_id = message_id
        self.pending_id = None
        self.deadline = None
        self._persist()
        print("Получено новое входящее сообщение. Ждём, пока ты его прочитаешь.")

    async def _refresh_pending(self) -> bool:
        if await self.conversation.incoming_is_read(self.last_incoming_id):
            if self.pending_id != self.last_incoming_id:
                self.pending_id = self.last_incoming_id
                self._persist()
            return True
        return bool(self.pending_id)

    async def on_inbox_read(self, max_id: int) -> None:
        if not self.last_incoming_id or max_id < self.last_incoming_id:
            return
        self.pending_id = self.last_incoming_id
        await self.schedule_after_read("Ты прочитал её сообщение")

    async def schedule_after_read(self, reason: str) -> None:
        if not await self._refresh_pending():
            print(f"{reason}: удаление не нужно, нет прочитанного входящего сообщения.")
            return
        self.deadline = time.time() + self.grace_period_seconds
        self._persist()
        print(
            f"{reason}: запускаем таймер на {_duration_label(self.grace_period_seconds)}. "
            "Если контакт появится онлайн, удаление отменится."
        )

    def on_partner_online(self) -> None:
        if not self.pending_id:
            return
        self.pending_id = None
        self.deadline = None
        self._persist()
        print("Контакт появился онлайн. Ожидание удаления отменено до следующего нового сообщения.")

    def on_typing_cancel(self) -> None:
        self.last_typing_report_key = None

    async def on_typing(self) -> None:
        unread, read_max = await self.conversation.unread_outgoing(
            self.typing_unread_limit, self.outgoing_scan_limit
        )
        report_key = tuple(message.id for message in unread)
        if report_key == self.last_typing_report_key:
            return
        print(
            f"Она печатает: непрочитанные ею твои сообщения есть: "
            f"{'да' if unread else 'нет'} (read_outbox_max_id={read_max})."
        )
        if unread:
            print(f"  - ID непрочитанных сообщений: {', '.join(str(message.id) for message in unread)}")
        self.last_typing_report_key = report_key

    async def _export_and_delete(self, reason: str) -> bool:
        async with self.sync_lock:
            print(f"{reason}: экспортируем и удаляем чат...")
            expected_id = self.last_incoming_id
            filename, message_ids = await self.sync_archive()
            latest_id = await self.conversation.latest_message_id()
            if (
                self.last_incoming_id != expected_id
                or await self.conversation.latest_incoming_id() != expected_id
                or (latest_id is not None and latest_id > max(message_ids, default=0))
                or not await self.conversation.incoming_is_read(expected_id)
            ):
                self.archive.log_deletion(
                    reason, len(message_ids), "cancelled", "Chat changed during export"
                )
                print("Чат изменился во время экспорта; удаление отменено.")
                return False

            await self.delete_snapshot(reason, message_ids)
            if message_ids:
                print(f"Чат обработан. Бэкап: {filename}")
            return True

    async def maybe_delete_after_grace_period(self, reason: str) -> None:
        if not self.last_incoming_id:
            return
        if not await self._refresh_pending():
            return
        if self.deadline is None or time.time() < self.deadline:
            return
        if await self._export_and_delete(reason) and self.last_incoming_id == self.pending_id:
            self.last_incoming_id = None
            self.pending_id = None
            self.deadline = None
            self._persist()

    async def run_recheck_loop(self) -> None:
        while True:
            await asyncio.sleep(self.recheck_seconds)
            if not self.last_incoming_id or not self.pending_id or self.deadline is None:
                continue
            if time.time() < self.deadline:
                continue
            try:
                await self.maybe_delete_after_grace_period("Фоновая проверка")
            except Exception as exc:
                print(f"Удаление отложено из-за ошибки архива или Telegram: {exc}")
                await asyncio.sleep(60)
