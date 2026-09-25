"""Telegram conversation archiving and verified snapshot deletion."""

import os
import re
import uuid
from pathlib import Path

from telethon.tl.types import (
    MessageEntityBold,
    MessageEntityCode,
    MessageEntityItalic,
    MessageEntityMention,
    MessageEntityTextUrl,
    MessageEntityUrl,
)

from couplebot.storage.archive import ArchiveError, ArchiveStore


def _build_entities(msg) -> list[dict]:
    if not msg.text:
        return []
    if not msg.entities:
        return [{"type": "plain", "text": msg.text}]

    result = []
    for entity in msg.entities:
        text = msg.text[entity.offset : entity.offset + entity.length]
        if isinstance(entity, MessageEntityBold):
            result.append({"type": "bold", "text": text})
        elif isinstance(entity, MessageEntityItalic):
            result.append({"type": "italic", "text": text})
        elif isinstance(entity, MessageEntityCode):
            result.append({"type": "code", "text": text})
        elif isinstance(entity, MessageEntityUrl):
            result.append({"type": "link", "text": text})
        elif isinstance(entity, MessageEntityTextUrl):
            result.append({"type": "text_link", "text": text, "href": entity.url})
        elif isinstance(entity, MessageEntityMention):
            result.append({"type": "mention", "text": text})
        else:
            result.append({"type": "plain", "text": text})
    return result


def _pluralize_ru(value: int, one: str, few: str, many: str) -> str:
    value = abs(value)
    if value % 10 == 1 and value % 100 != 11:
        return one
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return few
    return many


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


async def _download_media(telegram_client, msg, archive: ArchiveStore) -> str | None:
    if not getattr(msg, "file", None):
        media = getattr(msg, "media", None)
        if media is not None and type(media).__name__ != "MessageMediaWebPage":
            raise ArchiveError(f"Message {msg.id} has unsupported media; chat kept intact")
        return None

    extension = getattr(msg.file, "ext", None) or ".bin"
    if not re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", extension):
        extension = ".bin"
    archive.media_dir.mkdir(parents=True, exist_ok=True)
    destination = archive.media_dir / f"{msg.id}{extension}"
    if destination.is_file() and destination.stat().st_size:
        return destination.relative_to(archive.data_dir).as_posix()

    temporary = archive.media_dir / f".{msg.id}-{uuid.uuid4().hex}{extension}"
    try:
        downloaded = await telegram_client.download_media(msg, file=str(temporary))
        if not downloaded:
            raise ArchiveError(f"Media download failed for message {msg.id}")
        downloaded_path = Path(downloaded)
        if not downloaded_path.is_file() or downloaded_path.stat().st_size == 0:
            raise ArchiveError(f"Media download is empty for message {msg.id}")
        with downloaded_path.open("rb") as source:
            os.fsync(source.fileno())
        os.replace(downloaded_path, destination)
        _sync_directory(archive.media_dir)
    finally:
        temporary.unlink(missing_ok=True)

    return destination.relative_to(archive.data_dir).as_posix()


async def sync_conversation(
    telegram_client, partner, archive: ArchiveStore
) -> tuple[Path, list[int]]:
    """Archive all current conversation messages, then verify and export them."""
    live_ids = []
    messages = []
    async for msg in telegram_client.iter_messages(partner, reverse=True):
        live_ids.append(msg.id)
        sender = await msg.get_sender()
        sender_name = (
            f"{getattr(sender, 'first_name', '') or ''} "
            f"{getattr(sender, 'last_name', '') or ''}"
        ).strip()
        message = {
            "id": msg.id,
            "type": "message",
            "date": msg.date.strftime("%Y-%m-%dT%H:%M:%S"),
            "date_unixtime": str(int(msg.date.timestamp())),
            "from": sender_name,
            "from_id": f"user{getattr(sender, 'id', None) or msg.sender_id}",
            "text": msg.text or "",
            "text_entities": _build_entities(msg),
        }

        if msg.reply_to_msg_id:
            message["reply_to_message_id"] = msg.reply_to_msg_id
        if msg.edit_date:
            message["edited"] = msg.edit_date.strftime("%Y-%m-%dT%H:%M:%S")

        media_path = await _download_media(telegram_client, msg, archive)
        if msg.photo:
            message["photo"] = media_path
        elif media_path:
            message["file"] = media_path
        if msg.sticker:
            message["media_type"] = "sticker"
            message["sticker_emoji"] = next(
                (
                    getattr(attribute, "alt", "")
                    for attribute in msg.sticker.attributes
                    if getattr(attribute, "alt", "")
                ),
                "",
            )
        elif msg.voice:
            message["media_type"] = "voice_message"
            message["duration_seconds"] = (
                msg.voice.attributes[0].duration if msg.voice.attributes else 0
            )
        elif msg.video:
            message["media_type"] = "video_file"
        elif media_path:
            message["media_type"] = "file"

        messages.append(message)
        if len(messages) >= 250:
            archive.save_messages(messages)
            messages.clear()

    if messages:
        archive.save_messages(messages)
    archive.verify_messages(live_ids)
    filename = archive.write_json_export()
    print(f"Архив обновлён: {len(live_ids)} сообщений сейчас в чате → {filename}")
    return filename, live_ids


async def delete_archived_snapshot(
    telegram_client,
    partner,
    archive: ArchiveStore,
    reason: str,
    message_ids: list[int],
    dry_run: bool,
) -> None:
    """Delete only an archived ID snapshot and verify those IDs are gone."""
    if dry_run:
        archive.log_deletion(reason, len(message_ids), "preview")
        count = len(message_ids)
        print(
            f"Пробный запуск: в архиве {count} "
            f"{_pluralize_ru(count, 'сообщение', 'сообщения', 'сообщений')} "
            "из чата; ничего не удалено."
        )
        return

    if not message_ids:
        return

    archive.log_deletion(reason, len(message_ids), "started")
    try:
        await telegram_client.delete_messages(partner, message_ids, revoke=True)
        archived_ids = set(message_ids)
        remaining = set()
        async for msg in telegram_client.iter_messages(partner):
            if msg.id in archived_ids:
                remaining.add(msg.id)
        if remaining:
            raise ArchiveError(f"{len(remaining)} messages remain after deletion")
    except Exception as exc:
        archive.log_deletion(reason, len(message_ids), "failed", str(exc))
        raise
    archive.log_deletion(reason, len(message_ids), "completed")
