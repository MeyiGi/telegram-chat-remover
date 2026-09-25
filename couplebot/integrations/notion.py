"""Notion API support for daily diary pages."""

from __future__ import annotations

import asyncio
import re
from datetime import date

from couplebot.integrations.http import ExternalServiceError, request_json

DiaryError = ExternalServiceError
_request_json = request_json


def _rich_text(content: str) -> list[dict]:
    # Notion rich-text content is limited to 2000 characters per text object.
    return [
        {"type": "text", "text": {"content": content[index : index + 1900]}}
        for index in range(0, len(content), 1900)
    ] or [{"type": "text", "text": {"content": ""}}]


def markdown_to_notion_blocks(markdown: str) -> list[dict]:
    blocks = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"\\?[*_`]", "", line)
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            block_type = f"heading_{level}"
            blocks.append({block_type: {"rich_text": _rich_text(heading.group(2))}})
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet:
            blocks.append(
                {"bulleted_list_item": {"rich_text": _rich_text(bullet.group(1))}}
            )
            continue
        numbered = re.match(r"^\d+[.)]\s+(.+)$", line)
        if numbered:
            blocks.append(
                {"numbered_list_item": {"rich_text": _rich_text(numbered.group(1))}}
            )
            continue
        for index in range(0, len(line), 1900):
            blocks.append(
                {"paragraph": {"rich_text": _rich_text(line[index : index + 1900])}}
            )
    return blocks or [{"paragraph": {"rich_text": _rich_text("Нет записи")}}]


class NotionDiaryWriter:
    def __init__(
        self,
        token: str,
        parent_page_id: str | None = None,
        data_source_id: str | None = None,
        title_property: str = "Name",
        api_version: str = "2026-03-11",
        endpoint: str = "https://api.notion.com/v1/pages",
    ):
        if not parent_page_id and not data_source_id:
            raise DiaryError("Notion diary parent is not configured")
        self.token = token
        self.parent_page_id = parent_page_id
        self.data_source_id = data_source_id
        self.title_property = title_property
        self.api_version = api_version
        self.endpoint = endpoint
        self.api_root = endpoint.rsplit("/", 1)[0]

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.api_version,
        }

    async def _children(self, parent_id: str) -> list[dict]:
        children: list[dict] = []
        cursor = None
        while True:
            url = f"{self.api_root}/blocks/{parent_id}/children?page_size=100"
            if cursor:
                url += f"&start_cursor={cursor}"
            response = await asyncio.to_thread(
                _request_json, url, self._headers, None, 90, "GET"
            )
            children.extend(response.get("results", []))
            if not response.get("has_more"):
                return children
            cursor = response.get("next_cursor")
            if not cursor:
                raise DiaryError("Notion returned no pagination cursor")

    async def _find_or_create_child_page(
        self, parent_id: str, title: str, title_prefix: str | None = None
    ) -> str:
        for block in await self._children(parent_id):
            child_page = block.get("child_page")
            existing_title = child_page.get("title", "") if child_page else ""
            if existing_title == title or (
                title_prefix and existing_title.startswith(title_prefix)
            ):
                return block["id"]

        payload = {
            "parent": {"type": "page_id", "page_id": parent_id},
            "properties": {"title": {"title": _rich_text(title)}},
        }
        response = await asyncio.to_thread(
            _request_json, self.endpoint, self._headers, payload
        )
        page_id = response.get("id")
        if not page_id:
            raise DiaryError(f"Notion returned no page id for {title}")
        return page_id

    async def _append_blocks(self, page_id: str, blocks: list[dict]) -> None:
        # Keep the marker and entry in one API request, so a retry cannot
        # mistake a partly appended entry for a completed one.
        if len(blocks) > 100:
            raise DiaryError("Notion diary entry exceeds 100 blocks")
        await asyncio.to_thread(
            _request_json,
            f"{self.api_root}/blocks/{page_id}/children",
            self._headers,
            {"children": blocks},
            90,
            "PATCH",
        )

    async def _find_data_source_page(self, title: str) -> str | None:
        assert self.data_source_id
        cursor = None
        while True:
            payload = {
                "filter": {
                    "property": self.title_property,
                    "title": {"equals": title},
                },
                "page_size": 100,
            }
            if cursor:
                payload["start_cursor"] = cursor
            response = await asyncio.to_thread(
                _request_json,
                f"{self.api_root}/data_sources/{self.data_source_id}/query",
                self._headers,
                payload,
            )
            for page in response.get("results", []):
                if page.get("id"):
                    return page["id"]
            if not response.get("has_more"):
                return None
            cursor = response.get("next_cursor")
            if not cursor:
                raise DiaryError("Notion returned no pagination cursor")

    @staticmethod
    def _contains_marker(blocks: list[dict], marker: str) -> bool:
        for block in blocks:
            block_type = block.get("type")
            content = block.get(block_type, {}) if block_type else {}
            rich_text = content.get("rich_text", [])
            if marker in "".join(item.get("plain_text", "") for item in rich_text):
                return True
        return False

    async def create(self, diary_date: date, markdown: str, message_count: int) -> str:
        if self.data_source_id:
            title = f"Дневник — {diary_date.isoformat()}"
            marker = f"Автоматическая запись дневника · {diary_date.isoformat()}"
            title_value = {"title": [{"type": "text", "text": {"content": title}}]}
            parent = {"type": "data_source_id", "data_source_id": self.data_source_id}
            properties = {self.title_property: title_value}
            blocks = [
                {
                    "callout": {
                        "rich_text": _rich_text(marker),
                        "icon": {"emoji": "📔"},
                        "color": "blue_background",
                    }
                },
                {
                    "callout": {
                        "rich_text": _rich_text(f"Сообщений за день: {message_count}"),
                        "icon": {"emoji": "💬"},
                        "color": "gray_background",
                    }
                },
                *markdown_to_notion_blocks(markdown),
            ]
            if len(blocks) > 100:
                raise DiaryError("Notion diary entry exceeds 100 blocks")
            existing_page = await self._find_data_source_page(title)
            if existing_page:
                if not self._contains_marker(await self._children(existing_page), marker):
                    await self._append_blocks(existing_page, blocks)
                return existing_page
            payload = {"parent": parent, "properties": properties, "children": blocks}
            response = await asyncio.to_thread(
                _request_json, self.endpoint, self._headers, payload
            )
            page_id = response.get("id")
            if not page_id:
                raise DiaryError("Notion returned no page id")
            return page_id

        assert self.parent_page_id
        year_page = await self._find_or_create_child_page(
            self.parent_page_id, str(diary_date.year)
        )
        month_names = (
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
        )
        month_page = await self._find_or_create_child_page(
            year_page, month_names[diary_date.month - 1]
        )
        day_title = diary_date.strftime("%d.%m.%Y")
        day_page = await self._find_or_create_child_page(
            month_page, day_title, title_prefix=f"{day_title} -"
        )

        marker = f"Автоматическая запись дневника · {diary_date.isoformat()}"
        existing_blocks = await self._children(day_page)
        if self._contains_marker(existing_blocks, marker):
            return day_page

        blocks = [
            {
                "callout": {
                    "rich_text": _rich_text(marker),
                    "icon": {"emoji": "📔"},
                    "color": "blue_background",
                }
            },
            {
                "callout": {
                    "rich_text": _rich_text(
                        f"Сообщений за день: {message_count}"
                    ),
                    "icon": {"emoji": "💬"},
                    "color": "gray_background",
                }
            },
            *markdown_to_notion_blocks(markdown),
        ]
        await self._append_blocks(day_page, blocks)
        return day_page


__all__ = [
    "DiaryError",
    "NotionDiaryWriter",
    "_request_json",
    "markdown_to_notion_blocks",
]
