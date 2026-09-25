"""Application settings loaded once by the composition root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def _enabled(value: str) -> bool:
    return value.lower() in {"1", "true", "yes"}


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required setting: {name}")
    return value


@dataclass(frozen=True)
class AuthConfig:
    api_id: int
    api_hash: str
    my_phone: str
    telegram_session: str

    @classmethod
    def from_env(cls) -> AuthConfig:
        load_dotenv()
        return cls(
            api_id=int(_required("API_ID")),
            api_hash=_required("API_HASH"),
            my_phone=_required("MY_PHONE"),
            telegram_session=os.environ.get("TELEGRAM_SESSION", "karlis_listener"),
        )


@dataclass(frozen=True)
class AppConfig:
    api_id: int
    api_hash: str
    girlfriend_username: str
    my_phone: str
    my_export_name: str
    chat_display_name: str
    data_dir: Path
    telegram_session: str
    delete_dry_run: bool
    delete_grace_period_seconds: int
    background_recheck_interval_seconds: int
    typing_unread_messages_limit: int
    outgoing_read_scan_limit: int
    diary_enabled: bool
    diary_timezone: str
    diary_hour: int
    diary_max_messages: int
    groq_api_key: str
    groq_model: str
    notion_token: str
    notion_diary_parent_page_id: str
    notion_diary_data_source_id: str
    notion_diary_title_property: str

    @classmethod
    def from_env(cls) -> AppConfig:
        auth = AuthConfig.from_env()
        diary_timezone = os.environ.get("DIARY_TIMEZONE", "Asia/Bishkek").strip() or "Asia/Bishkek"
        ZoneInfo(diary_timezone)
        diary_hour = int(os.environ.get("DIARY_HOUR", "5"))
        if not 0 <= diary_hour <= 23:
            raise ValueError("DIARY_HOUR must be between 0 and 23")
        return cls(
            api_id=auth.api_id,
            api_hash=auth.api_hash,
            girlfriend_username=_required("GIRLFRIEND_USERNAME"),
            my_phone=auth.my_phone,
            my_export_name=os.environ.get("MY_EXPORT_NAME", "Даниэл").strip() or "Даниэл",
            chat_display_name=os.environ.get("CHAT_DISPLAY_NAME", "Женушка чат").strip() or "Женушка чат",
            data_dir=Path(os.environ.get("DATA_DIR", "data")),
            telegram_session=auth.telegram_session,
            delete_dry_run=_enabled(os.environ.get("DELETE_DRY_RUN", "0")),
            delete_grace_period_seconds=30 * 60,
            background_recheck_interval_seconds=2,
            typing_unread_messages_limit=20,
            outgoing_read_scan_limit=100,
            diary_enabled=_enabled(os.environ.get("DIARY_ENABLED", "1")),
            diary_timezone=diary_timezone,
            diary_hour=diary_hour,
            diary_max_messages=int(os.environ.get("DIARY_MAX_MESSAGES", "500")),
            groq_api_key=os.environ.get("GROQ_API_KEY", "").strip(),
            groq_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
            notion_token=(
                os.environ.get("NOTION_TOKEN", "").strip()
                or os.environ.get("NOTION_API_KEY", "").strip()
            ),
            notion_diary_parent_page_id=(
                os.environ.get("NOTION_DIARY_PARENT_PAGE_ID", "").strip()
                or os.environ.get("NOTION_PARENT_PAGE_ID", "").strip()
            ),
            notion_diary_data_source_id=(
                os.environ.get("NOTION_DIARY_DATA_SOURCE_ID", "").strip()
                or os.environ.get("NOTION_DIARY_DATABASE_ID", "").strip()
            ),
            notion_diary_title_property=(
                os.environ.get("NOTION_DIARY_TITLE_PROPERTY", "Name").strip() or "Name"
            ),
        )
