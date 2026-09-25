"""Groq-backed diary text generation."""

from __future__ import annotations

import asyncio
from datetime import date

from couplebot.integrations.http import ExternalServiceError, request_json


class GroqDiaryWriter:
    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        endpoint: str = "https://api.groq.com/openai/v1/chat/completions",
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    async def write(self, diary_date: date, transcript: str) -> str:
        prompt = f"""Дата дневника: {diary_date.isoformat()}

Ниже находится переписка за этот день. Напиши личную дневниковую запись на русском языке.
Опирайся только на сообщения. Не придумывай факты, людей, события или чувства.
Если настроение нельзя уверенно определить, скажи об этом осторожно.
Пиши тепло, спокойно и конкретно, без упоминания искусственного интеллекта.
Используй Markdown с короткими разделами:
## Итог дня
## Важные моменты
## Настроение и отношения
## Желания и планы
## Что запомнить

Если сообщений нет, создай короткую запись о том, что в этот день в архиве нет переписки.

Переписка:
{transcript}
"""
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты аккуратный автор личного дневника пары.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.35,
            "max_completion_tokens": 1800,
            "stream": False,
        }
        response = await asyncio.to_thread(
            request_json,
            self.endpoint,
            {"Authorization": f"Bearer {self.api_key}"},
            payload,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ExternalServiceError("Groq returned no diary text") from exc
        if not isinstance(content, str) or not content.strip():
            raise ExternalServiceError("Groq returned an empty diary")
        return content.strip()


__all__ = ["GroqDiaryWriter"]
