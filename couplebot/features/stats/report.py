"""Statistics report generation for an exported Telegram conversation."""

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
from statistics import median


def pluralize_ru(value: int, one: str, few: str, many: str) -> str:
    value = abs(value)
    if value % 10 == 1 and value % 100 != 11:
        return one
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return few
    return many


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "нет данных"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} сек"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} мин {sec} сек" if sec else f"{minutes} мин"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} ч {minutes} мин" if minutes else f"{hours} ч"
    days, hours = divmod(hours, 24)
    return f"{days} д {hours} ч" if hours else f"{days} д"


def chunk_text(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            chunks.append("".join(current).rstrip())
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)

    if current:
        chunks.append("".join(current).rstrip())
    return chunks


def message_preview_text(msg, limit: int = 80) -> str:
    text = (getattr(msg, "message", None) or getattr(msg, "text", None) or "").strip()
    if text:
        text = re.sub(r"\s+", " ", text)
        return text if len(text) <= limit else f"{text[:limit - 3]}..."
    if getattr(msg, "sticker", None):
        return "[стикер]"
    if getattr(msg, "voice", None):
        return "[голосовое]"
    if getattr(msg, "video", None):
        return "[видео]"
    if getattr(msg, "photo", None):
        return "[фото]"
    if getattr(msg, "file", None):
        return "[файл]"
    return "[без текста]"


def _format_share(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round(part / total * 100)}%"


def _format_count(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _normalize_export_sender(
    raw_name: str | None, chat_name: str, my_export_name: str
) -> str:
    sender_name = (raw_name or "").strip()
    if sender_name == my_export_name:
        return "Ты"
    return chat_name or "Женушка чат"


def _load_export_messages(export_file: Path) -> tuple[dict, list[dict]]:
    if not export_file.exists():
        return {}, []

    with export_file.open(encoding="utf-8") as f:
        export = json.load(f)

    messages = export.get("messages", [])
    messages.sort(key=lambda item: item.get("id", 0))
    return export, messages


def build_statistics_from_export(
    export_file: Path, chat_display_name: str, my_export_name: str
) -> str:
    weekday_names = {
        "Monday": "понедельник",
        "Tuesday": "вторник",
        "Wednesday": "среда",
        "Thursday": "четверг",
        "Friday": "пятница",
        "Saturday": "суббота",
        "Sunday": "воскресенье",
    }
    export, raw_messages = _load_export_messages(export_file)
    if not raw_messages:
        return "В архиве пока нет сообщений."

    chat_name = chat_display_name
    total_entries = len(raw_messages)
    total = 0
    service_total = 0
    by_sender: Counter = Counter()
    by_day: Counter = Counter()
    by_hour: Counter = Counter()
    by_month: Counter = Counter()
    by_date: Counter = Counter()
    photos = voices = videos = stickers = files = replies = edited = 0
    reactions_total = reaction_points = forwarded = links = mentions = 0
    service_actions: Counter = Counter()
    word_counter: Counter = Counter()
    emoji_counter: Counter = Counter()
    total_chars = 0
    longest_msg = ""
    longest_msg_sender = "?"
    total_words = 0
    first_dt = None
    last_dt = None
    first_text = ""
    last_text = ""
    active_dates: set = set()
    message_lengths = []
    response_times = []
    previous_sender = None
    previous_dt = None
    previous_message_dt = None
    previous_message_sender = None
    conversation_streak = 0
    max_conversation_streak = 0
    max_streak_sender = "?"
    night_messages = 0
    morning_messages = 0
    weekend_messages = 0
    longest_silence_seconds = None
    longest_silence_start = None
    longest_silence_end = None
    first_message_sender = "?"
    last_message_sender = "?"

    for msg in raw_messages:
        msg_type = msg.get("type")
        text_value = msg.get("text", "")
        text = (
            text_value
            if isinstance(text_value, str)
            else "".join(
                part if isinstance(part, str) else part.get("text", "")
                for part in text_value
            )
        )
        date_raw = msg.get("date")
        dt = None
        if date_raw:
            try:
                dt = datetime.fromisoformat(date_raw)
            except ValueError:
                dt = None

        if msg_type == "service":
            service_total += 1
            if msg.get("action"):
                service_actions[msg["action"]] += 1
        if msg_type != "message":
            continue

        total += 1
        sender_name = _normalize_export_sender(
            msg.get("from") or msg.get("actor"), chat_name, my_export_name
        )
        by_sender[sender_name] += 1
        last_message_sender = sender_name
        if total == 1:
            first_message_sender = sender_name

        if msg.get("edited"):
            edited += 1
        if msg.get("reply_to_message_id"):
            replies += 1
        if msg.get("forwarded_from") or msg.get("forwarded_from_id"):
            forwarded += 1
        if msg.get("photo"):
            photos += 1
        media_type = msg.get("media_type")
        if media_type == "voice_message":
            voices += 1
        elif media_type == "video_file":
            videos += 1
        elif media_type == "sticker":
            stickers += 1
        elif media_type and media_type not in {
            "voice_message",
            "video_file",
            "sticker",
        }:
            files += 1
        elif msg.get("file"):
            files += 1

        if dt:
            if first_dt is None:
                first_dt = dt
                first_text = text
            last_dt = dt
            last_text = text
            by_day[dt.strftime("%A")] += 1
            by_hour[dt.hour] += 1
            by_month[dt.strftime("%Y-%m")] += 1
            by_date[dt.date()] += 1
            active_dates.add(dt.date())
            if dt.weekday() >= 5:
                weekend_messages += 1
            if 0 <= dt.hour < 6:
                night_messages += 1
            if 6 <= dt.hour < 12:
                morning_messages += 1

            if previous_dt is not None:
                gap_seconds = (dt - previous_dt).total_seconds()
                if (
                    longest_silence_seconds is None
                    or gap_seconds > longest_silence_seconds
                ):
                    longest_silence_seconds = gap_seconds
                    longest_silence_start = previous_dt
                    longest_silence_end = dt
            previous_dt = dt

            if previous_message_sender == sender_name:
                conversation_streak += 1
            else:
                conversation_streak = 1
            if conversation_streak > max_conversation_streak:
                max_conversation_streak = conversation_streak
                max_streak_sender = sender_name

            if (
                previous_message_sender
                and previous_message_sender != sender_name
                and previous_message_dt
            ):
                response_times.append((dt - previous_message_dt).total_seconds())
            previous_message_dt = dt
            previous_message_sender = sender_name

        if text:
            total_chars += len(text)
            message_lengths.append(len(text))
            if len(text) > len(longest_msg):
                longest_msg = text
                longest_msg_sender = sender_name
            words = re.findall(r"[а-яёa-z0-9]{3,}", text.lower())
            word_counter.update(words)
            total_words += len(re.findall(r"\S+", text))
            links += len(re.findall(r"https?://|t\.me/|www\.", text.lower()))
            mentions += len(re.findall(r"@\w+", text))
            emoji_counter.update(
                re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text)
            )
        else:
            message_lengths.append(0)

        for reaction in msg.get("reactions", []):
            count = int(reaction.get("count", 0) or 0)
            emoji = reaction.get("emoji") or reaction.get("type") or "?"
            reactions_total += count
            reaction_points += 1
            emoji_counter[emoji] += count

    if total == 0 or first_dt is None or last_dt is None:
        return "В архиве пока нет обычных сообщений."

    first_date = first_dt.strftime("%Y-%m-%d %H:%M")
    last_date = last_dt.strftime("%Y-%m-%d %H:%M")
    days_total = max((last_dt.date() - first_dt.date()).days + 1, 1)
    avg_per_day = round(total / days_total, 1)

    top_hours = by_hour.most_common(3)
    peak_hour = (
        f"{top_hours[0][0]:02d}:00–{top_hours[0][0]+1:02d}:00" if top_hours else "?"
    )
    peak_month = by_month.most_common(1)[0][0] if by_month else "?"
    peak_day = weekday_names.get(by_day.most_common(1)[0][0], "?") if by_day else "?"
    quiet_hour = f"{by_hour.most_common()[-1][0]:02d}:00" if by_hour else "?"
    top_words = word_counter.most_common(6)
    top_emojis = emoji_counter.most_common(5)

    names = list(by_sender.keys())
    name1 = names[0] if len(names) > 0 else "?"
    name2 = names[1] if len(names) > 1 else "?"
    count1 = by_sender[name1]
    count2 = by_sender[name2]
    avg_chars = round(total_chars / total, 1) if total else 0
    avg_words = round(total_words / total, 1) if total else 0
    longest_preview = (
        (longest_msg[:80] + "...") if len(longest_msg) > 80 else longest_msg
    )
    first_preview = (
        (first_text[:60] + "...")
        if len(first_text) > 60
        else (first_text or "без текста")
    )
    last_preview = (
        (last_text[:60] + "...") if len(last_text) > 60 else (last_text or "без текста")
    )
    active_days_count = len(active_dates)
    top_day_lines = (
        ", ".join(f"{hour:02d}:00" for hour, _ in top_hours[:3]) if top_hours else "?"
    )
    total_media = photos + voices + videos + stickers + files
    dominant_name = name1 if count1 >= count2 else name2
    dominant_count = max(count1, count2)
    dominant_share = _format_share(dominant_count, total)
    avg_active_day = round(total / active_days_count, 1) if active_days_count else 0
    relationship_days = days_total
    relationship_label = pluralize_ru(relationship_days, "день", "дня", "дней")
    top_words_line = (
        ", ".join(f"{word} ({count})" for word, count in top_words)
        if top_words
        else "нет данных"
    )
    top_emoji_line = (
        ", ".join(f"{emoji} ({count})" for emoji, count in top_emojis)
        if top_emojis
        else "нет данных"
    )
    median_chars = int(median(message_lengths)) if message_lengths else 0
    longest_day, longest_day_count = by_date.most_common(1)[0]
    quiet_day, quiet_day_count = min(by_date.items(), key=lambda item: item[1])
    avg_response = (
        format_duration(sum(response_times) / len(response_times))
        if response_times
        else "нет данных"
    )
    fastest_response = (
        format_duration(min(response_times)) if response_times else "нет данных"
    )
    longest_silence = format_duration(longest_silence_seconds)
    weekend_share = _format_share(weekend_messages, total)
    night_share = _format_share(night_messages, total)
    morning_share = _format_share(morning_messages, total)
    service_line = (
        ", ".join(
            f"{action} ({count})" for action, count in service_actions.most_common(4)
        )
        if service_actions
        else "нет"
    )
    response_switches = len(response_times)

    lines = [
        f"📊 Статистика чата: {chat_name}",
        "",
        f"За период с {first_date} по {last_date} у вас накопилось {_format_count(total)} "
        f"{pluralize_ru(total, 'сообщение', 'сообщения', 'сообщений')} за {relationship_days} {relationship_label}.",
        f"Записей в экспорте: {_format_count(total_entries)}. Сервисных событий: {_format_count(service_total)}.",
        f"В среднем это {avg_per_day} в день или {avg_active_day} в активный день.",
        "",
        "Кто тащит диалог:",
        f"{dominant_name} отправил(а) больше всех: {_format_count(dominant_count)} сообщений ({dominant_share} от чата).",
        f"{name1}: {_format_count(count1)} | {name2}: {_format_count(count2)}",
        f"Первое обычное сообщение отправил(а): {first_message_sender}. Последнее: {last_message_sender}.",
        "",
        "Ритм общения:",
        f"Самый жаркий час: {peak_hour}. Тихий час: {quiet_hour}.",
        f"Чаще всего вы пишете в {peak_day}. Топ часов: {top_day_lines}.",
        f"Самый активный месяц: {peak_month}. Активных дней: {_format_count(active_days_count)}.",
        f"Самый плотный день: {longest_day} ({longest_day_count}). Самый тихий активный день: {quiet_day} ({quiet_day_count}).",
        f"Ночных сообщений: {_format_count(night_messages)} ({night_share}). Утренних: {_format_count(morning_messages)} ({morning_share}). Выходных: {_format_count(weekend_messages)} ({weekend_share}).",
        "",
        "Что летает в чат:",
        f"Медиа всего: {_format_count(total_media)}. Фото: {photos}, голосовые: {voices}, видео: {videos}, "
        f"стикеры: {stickers}, файлы: {files}.",
        f"Ответов на сообщения: {_format_count(replies)}. Пересланных сообщений: {_format_count(forwarded)}. Отредактированных: {_format_count(edited)}.",
        f"Реакций получено: {_format_count(reactions_total)} по {_format_count(reaction_points)} сообщениям. Сервисные события: {service_line}.",
        "",
        "Текстовый портрет:",
        f"Всего символов: {_format_count(total_chars)}. Средняя длина сообщения: {avg_chars} символа и {avg_words} слова.",
        f"Медианная длина: {median_chars} символов. Ссылок: {_format_count(links)}. Упоминаний: {_format_count(mentions)}.",
        f"Частые слова: {top_words_line}.",
        f"Частые эмодзи и реакции: {top_emoji_line}.",
        f"Самое длинное сообщение: {len(longest_msg)} символов, отправил(а) {longest_msg_sender}.",
        f"\"{longest_preview or 'без текста'}\"",
        "",
        "Динамика:",
        f"Средняя скорость ответа между вами: {avg_response}. Самый быстрый ответ: {fastest_response}. Переключений между собеседниками: {_format_count(response_switches)}.",
        f"Самая длинная серия подряд: {_format_count(max_conversation_streak)} сообщений от {max_streak_sender}.",
        f"Самая длинная пауза: {longest_silence}.",
        f"Пауза была между {longest_silence_start.strftime('%Y-%m-%d %H:%M') if longest_silence_start else '?'} и {longest_silence_end.strftime('%Y-%m-%d %H:%M') if longest_silence_end else '?'}.",
        "",
        "Начало и финал:",
        f'Первое сообщение: "{first_preview}"',
        f'Последнее сообщение: "{last_preview}"',
    ]
    return "\n".join(lines)
