import asyncio
import tempfile
import unittest
from datetime import date
from pathlib import Path

from archive_store import ArchiveStore
from daily_diary import DailyDiaryService, markdown_to_notion_blocks


class FakeGroq:
    def __init__(self):
        self.calls = []

    async def write(self, diary_date, transcript):
        self.calls.append((diary_date, transcript))
        return "## Итог дня\n- Мы поговорили и всё записалось."


class FakeNotion:
    def __init__(self):
        self.calls = []

    async def create(self, diary_date, markdown, message_count):
        self.calls.append((diary_date, markdown, message_count))
        return "notion-page-id"


class DailyDiaryTests(unittest.TestCase):
    def test_markdown_is_converted_to_notion_blocks(self):
        blocks = markdown_to_notion_blocks("## Итог\n- Первый пункт\nОбычный текст")
        self.assertEqual(list(blocks[0]), ["heading_2"])
        self.assertEqual(list(blocks[1]), ["bulleted_list_item"])
        self.assertEqual(list(blocks[2]), ["paragraph"])

    def test_daily_page_is_created_once_for_a_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = ArchiveStore(Path(temporary), 42, "Friend")
            archive.save_messages(
                [
                    {
                        "id": 1,
                        "type": "message",
                        "date": "2026-09-21T10:00:00",
                        "from": "Friend",
                        "text": "Сегодня было хорошо",
                    }
                ]
            )
            groq = FakeGroq()
            notion = FakeNotion()
            sync_calls = []

            async def sync():
                sync_calls.append(True)

            service = DailyDiaryService(
                archive,
                groq,
                notion,
                "Asia/Bishkek",
                sync_callback=sync,
            )
            first = asyncio.run(service.create_for_date(date(2026, 9, 21)))
            second = asyncio.run(service.create_for_date(date(2026, 9, 21)))

            self.assertEqual(first, "notion-page-id")
            self.assertIsNone(second)
            self.assertEqual(len(sync_calls), 1)
            self.assertEqual(len(groq.calls), 1)
            self.assertEqual(len(notion.calls), 1)
            self.assertIn("Сегодня было хорошо", groq.calls[0][1])
            self.assertEqual(archive.diary_status(date(2026, 9, 21)), "completed")
            archive.close()


if __name__ == "__main__":
    unittest.main()
