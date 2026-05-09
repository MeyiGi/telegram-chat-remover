import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError, PhoneNumberInvalidError
from dotenv import load_dotenv
import os

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
MY_PHONE = os.environ["MY_PHONE"]

async def main():
    client = TelegramClient("karlis_listener", API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Уже авторизован как: {me.first_name} ({me.phone})")
        await client.disconnect()
        return

    print(f"Отправляю код на {MY_PHONE}...")
    try:
        result = await client.send_code_request(MY_PHONE)
        print(f"Код отправлен. Тип: {result.type.__class__.__name__}")
    except FloodWaitError as e:
        print(f"RATE LIMIT: нужно ждать {e.seconds} сек ({e.seconds//60} мин)")
        await client.disconnect()
        return
    except PhoneNumberInvalidError:
        print("ОШИБКА: номер недействителен")
        await client.disconnect()
        return

    code = input("Введи код из Telegram: ")
    try:
        await client.sign_in(MY_PHONE, code)
    except SessionPasswordNeededError:
        password = input("Введи пароль 2FA: ")
        await client.sign_in(password=password)

    me = await client.get_me()
    print(f"Успешно! Авторизован как: {me.first_name} ({me.phone})")
    print("Сессия сохранена — теперь запускай python3 main.py")
    await client.disconnect()

asyncio.run(main())
