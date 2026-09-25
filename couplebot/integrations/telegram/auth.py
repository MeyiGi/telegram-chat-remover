"""Interactive Telegram session authorization."""

from __future__ import annotations

from telethon.errors import (
    FloodWaitError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)


async def authorize(client, phone: str) -> None:
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Уже авторизован как: {me.first_name}")
            return

        print("Отправляю код Telegram...")
        try:
            result = await client.send_code_request(phone)
            print(f"Код отправлен. Тип: {result.type.__class__.__name__}")
        except FloodWaitError as exc:
            print(f"RATE LIMIT: нужно ждать {exc.seconds} сек ({exc.seconds // 60} мин)")
            return
        except PhoneNumberInvalidError:
            print("ОШИБКА: номер недействителен")
            return

        code = input("Введи код из Telegram: ")
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("Введи пароль 2FA: ")
            await client.sign_in(password=password)

        me = await client.get_me()
        print(f"Успешно! Авторизован как: {me.first_name}")
        print("Сессия сохранена — теперь запускай python3 main.py")
    finally:
        await client.disconnect()
