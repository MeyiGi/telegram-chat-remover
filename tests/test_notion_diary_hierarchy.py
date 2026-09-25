import asyncio
import unittest
from datetime import date
from unittest.mock import patch

from couplebot.integrations.notion import DiaryError, NotionDiaryWriter


class FakeNotionApi:
    def __init__(self):
        self.children = {
            "root": [{"id": "year", "type": "child_page", "child_page": {"title": "2026"}}],
            "year": [{"id": "month", "type": "child_page", "child_page": {"title": "Сентябрь"}}],
            "month": [
                {
                    "id": "day",
                    "type": "child_page",
                    "child_page": {"title": "24.09.2026 - важный день"},
                }
            ],
            "day": [
                {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Ручная запись"}]}}
            ],
        }
        self.append_count = 0
        self.created = []

    def request(self, url, headers, payload=None, timeout=90, method="POST"):
        if method == "GET":
            page_id = url.split("/blocks/", 1)[1].split("/", 1)[0]
            return {"results": self.children[page_id], "has_more": False}
        if method == "PATCH":
            page_id = url.split("/blocks/", 1)[1].split("/", 1)[0]
            self.append_count += 1
            for block in payload["children"]:
                kind = next(iter(block))
                plain_text = "".join(
                    item["text"]["content"] for item in block[kind]["rich_text"]
                )
                self.children[page_id].append(
                    {"type": kind, kind: {"rich_text": [{"plain_text": plain_text}]}}
                )
            return {"results": []}
        if method == "POST":
            parent_id = payload["parent"]["page_id"]
            title = "".join(
                item["text"]["content"] for item in payload["properties"]["title"]["title"]
            )
            page_id = f"created-{len(self.created) + 1}"
            self.children[parent_id].append(
                {"id": page_id, "type": "child_page", "child_page": {"title": title}}
            )
            self.children[page_id] = []
            self.created.append((parent_id, title, page_id))
            return {"id": page_id}
        raise AssertionError(f"Unexpected Notion {method} {url}")


class NotionDiaryHierarchyTests(unittest.TestCase):
    @staticmethod
    async def _inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    def test_reuses_existing_day_and_appends_only_once(self):
        api = FakeNotionApi()
        writer = NotionDiaryWriter("test-token", parent_page_id="root")
        with patch("couplebot.integrations.notion._request_json", new=api.request), patch(
            "couplebot.integrations.notion.asyncio.to_thread", new=self._inline
        ):
            first = asyncio.run(writer.create(date(2026, 9, 24), "## Итог дня\nВсё хорошо", 3))
            second = asyncio.run(writer.create(date(2026, 9, 24), "## Итог дня\nВсё хорошо", 3))
        self.assertEqual((first, second), ("day", "day"))
        self.assertEqual(api.append_count, 1)
        self.assertEqual(api.children["day"][0]["paragraph"]["rich_text"][0]["plain_text"], "Ручная запись")

    def test_creates_missing_month_and_day_under_existing_year(self):
        api = FakeNotionApi()
        api.children["year"] = []
        writer = NotionDiaryWriter("test-token", parent_page_id="root")
        with patch("couplebot.integrations.notion._request_json", new=api.request), patch(
            "couplebot.integrations.notion.asyncio.to_thread", new=self._inline
        ):
            day_page = asyncio.run(writer.create(date(2026, 9, 24), "## Итог дня", 1))
        self.assertEqual(
            api.created,
            [("year", "Сентябрь", "created-1"), ("created-1", "24.09.2026", "created-2")],
        )
        self.assertEqual(day_page, "created-2")
        self.assertEqual(api.append_count, 1)

    def test_data_source_retry_finds_page_after_lost_create_response(self):
        page = {"created": False, "create_count": 0, "blocks": []}

        def request(url, headers, payload=None, timeout=90, method="POST"):
            if url.endswith("/data_sources/source/query"):
                return {
                    "results": [{"id": "existing-page"}] if page["created"] else [],
                    "has_more": False,
                }
            if url.endswith("/pages"):
                page["create_count"] += 1
                page["created"] = True
                page["blocks"] = [
                    {
                        "type": next(iter(block)),
                        next(iter(block)): {
                            "rich_text": [
                                {"plain_text": item["text"]["content"]}
                                for item in block[next(iter(block))]["rich_text"]
                            ]
                        },
                    }
                    for block in payload["children"]
                ]
                raise DiaryError("response lost after create")
            if method == "GET" and url.endswith("/blocks/existing-page/children?page_size=100"):
                return {"results": page["blocks"], "has_more": False}
            raise AssertionError(f"Unexpected request: {method} {url}")

        writer = NotionDiaryWriter("test-token", data_source_id="source")
        with patch("couplebot.integrations.notion._request_json", new=request), patch(
            "couplebot.integrations.notion.asyncio.to_thread", new=self._inline
        ):
            with self.assertRaises(DiaryError):
                asyncio.run(writer.create(date(2026, 9, 24), "## Итог дня", 1))
            recovered = asyncio.run(writer.create(date(2026, 9, 24), "## Итог дня", 1))
        self.assertEqual(recovered, "existing-page")
        self.assertEqual(page["create_count"], 1)


if __name__ == "__main__":
    unittest.main()
