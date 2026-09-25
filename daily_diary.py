"""Compatibility imports for the daily diary pipeline."""

from couplebot.features.diary.service import (
    DailyDiaryService,
    DiaryError,
    _message_text,
    build_transcript,
    daily_diary_loop,
)
from couplebot.integrations.groq import GroqDiaryWriter
from couplebot.integrations.notion import (
    NotionDiaryWriter,
    _request_json,
    _rich_text,
    markdown_to_notion_blocks,
)

__all__ = [
    "DailyDiaryService",
    "DiaryError",
    "GroqDiaryWriter",
    "NotionDiaryWriter",
    "_message_text",
    "_request_json",
    "_rich_text",
    "build_transcript",
    "daily_diary_loop",
    "markdown_to_notion_blocks",
]
