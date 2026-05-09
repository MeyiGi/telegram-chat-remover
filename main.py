from telethon import TelegramClient, events
from telethon.tl.types import UserStatusOffline
from dotenv import load_dotenv
import json, asyncio, os
from datetime import datetime

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
GIRLFRIEND_USERNAME = os.environ["GIRLFRIEND_USERNAME"]
MY_PHONE = os.environ["MY_PHONE"]

client = TelegramClient("karlis_listener", API_ID, API_HASH)


async def export_telegram_format():
    partner = await client.get_entity(GIRLFRIEND_USERNAME)

    export = {
        "name": partner.first_name or GIRLFRIEND_USERNAME,
        "type": "personal_chat",
        "id": partner.id,
        "messages": [],
    }

    async for msg in client.iter_messages(GIRLFRIEND_USERNAME, reverse=True):
        sender = await msg.get_sender()
        sender_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()

        entities = []
        if msg.text:
            if msg.entities:
                for ent in msg.entities:
                    from telethon.tl.types import (
                        MessageEntityBold,
                        MessageEntityItalic,
                        MessageEntityCode,
                        MessageEntityUrl,
                        MessageEntityTextUrl,
                        MessageEntityMention,
                    )
                    ent_text = msg.text[ent.offset: ent.offset + ent.length]
                    if isinstance(ent, MessageEntityBold):
                        entities.append({"type": "bold", "text": ent_text})
                    elif isinstance(ent, MessageEntityItalic):
                        entities.append({"type": "italic", "text": ent_text})
                    elif isinstance(ent, MessageEntityCode):
                        entities.append({"type": "code", "text": ent_text})
                    elif isinstance(ent, MessageEntityUrl):
                        entities.append({"type": "link", "text": ent_text})
                    elif isinstance(ent, MessageEntityTextUrl):
                        entities.append({"type": "text_link", "text": ent_text, "href": ent.url})
                    elif isinstance(ent, MessageEntityMention):
                        entities.append({"type": "mention", "text": ent_text})
                    else:
                        entities.append({"type": "plain", "text": ent_text})
            else:
                entities = [{"type": "plain", "text": msg.text}]

        message = {
            "id": msg.id,
            "type": "message",
            "date": msg.date.strftime("%Y-%m-%dT%H:%M:%S"),
            "date_unixtime": str(int(msg.date.timestamp())),
            "from": sender_name,
            "from_id": f"user{sender.id}",
            "text": msg.text or "",
            "text_entities": entities,
        }

        if msg.reply_to_msg_id:
            message["reply_to_message_id"] = msg.reply_to_msg_id
        if msg.photo:
            message["photo"] = f"photos/photo_{msg.id}.jpg"
        if msg.sticker:
            message["media_type"] = "sticker"
            message["sticker_emoji"] = (
                msg.sticker.attributes[0].alt if msg.sticker.attributes else ""
            )
        if msg.voice:
            message["media_type"] = "voice_message"
            message["duration_seconds"] = (
                msg.voice.attributes[0].duration if msg.voice.attributes else 0
            )
        if msg.video:
            message["media_type"] = "video_file"

        export["messages"].append(message)

    filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=1)

    print(f"Сохранено {len(export['messages'])} сообщений → {filename}")
    return filename


async def monitor_and_clean():
    await client.start(
        phone=MY_PHONE,
        code_callback=lambda: input("Введи код из Telegram: "),
        password=lambda: input("Введи пароль 2FA: "),
    )
    print("Мониторинг запущен...")

    @client.on(events.UserUpdate(GIRLFRIEND_USERNAME))
    async def handler(event):
        if hasattr(event, "status") and isinstance(event.status, UserStatusOffline):
            print("Ушла офлайн — экспортируем...")
            filename = await export_telegram_format()

            msg_ids = []
            async for msg in client.iter_messages(GIRLFRIEND_USERNAME):
                msg_ids.append(msg.id)

            await client.delete_messages(GIRLFRIEND_USERNAME, msg_ids, revoke=True)
            print(f"Чат удалён. Бэкап: {filename}")

    await client.run_until_disconnected()


asyncio.run(monitor_and_clean())
