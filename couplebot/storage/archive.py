"""Durable local storage for the monitored Telegram conversation."""

import json
import os
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


class ArchiveError(RuntimeError):
    pass


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class ArchiveStore:
    def __init__(self, data_dir: Path, chat_id: int, chat_name: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chat_id = chat_id
        self.chat_name = chat_name
        self.export_path = self.data_dir / "chat_export.json"
        self.media_dir = self.data_dir / "media" / str(chat_id)
        self.database_path = self.data_dir / "archive.sqlite3"
        self.connection = sqlite3.connect(self.database_path)
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            );
            CREATE TABLE IF NOT EXISTS cleanup_state (
                chat_id INTEGER PRIMARY KEY,
                last_incoming_id INTEGER,
                pending_id INTEGER,
                deadline REAL
            );
            CREATE TABLE IF NOT EXISTS deletion_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reason TEXT NOT NULL,
                message_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS diary_runs (
                diary_date TEXT PRIMARY KEY,
                attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                notion_page_id TEXT,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS drive_media_uploads (
                relative_path TEXT PRIMARY KEY,
                drive_file_id TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._import_previous_export()

    def close(self) -> None:
        self.connection.close()

    def _import_previous_export(self) -> None:
        marker = f"imported_json_{self.chat_id}"
        if self.connection.execute(
            "SELECT 1 FROM metadata WHERE key = ?", (marker,)
        ).fetchone():
            return

        messages = []
        if self.export_path.exists():
            with self.export_path.open(encoding="utf-8") as source:
                previous = json.load(source)
            if int(previous.get("id", self.chat_id)) != self.chat_id:
                raise ArchiveError("Existing JSON export belongs to another chat")
            messages = previous.get("messages", [])
            if not isinstance(messages, list):
                raise ArchiveError("Existing JSON export has no message list")

        with self.connection:
            self.connection.executemany(
                "INSERT OR IGNORE INTO messages (chat_id, message_id, payload) VALUES (?, ?, ?)",
                (
                    (self.chat_id, int(message["id"]), json.dumps(message, ensure_ascii=False))
                    for message in messages
                ),
            )
            self.connection.execute(
                "INSERT INTO metadata (key, value) VALUES (?, '1')", (marker,)
            )

    def save_messages(self, messages: list[dict]) -> None:
        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO messages (chat_id, message_id, payload) VALUES (?, ?, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    (self.chat_id, int(message["id"]), json.dumps(message, ensure_ascii=False))
                    for message in messages
                ),
            )

    def verify_messages(self, live_ids: list[int]) -> None:
        for message_id in live_ids:
            row = self.connection.execute(
                "SELECT payload FROM messages WHERE chat_id = ? AND message_id = ?",
                (self.chat_id, message_id),
            ).fetchone()
            if row is None:
                raise ArchiveError(f"Live message {message_id} is missing from the archive")
            message = json.loads(row[0])
            for field in ("photo", "file"):
                relative = message.get(field)
                if not relative:
                    continue
                path = (self.data_dir / relative).resolve()
                if not path.is_relative_to(self.data_dir.resolve()):
                    raise ArchiveError(f"Unsafe media path for message {message_id}")
                if not path.is_file() or path.stat().st_size == 0:
                    raise ArchiveError(f"Media for message {message_id} is missing: {relative}")

    def pending_drive_media(self) -> list[tuple[str, Path]]:
        """Return existing archived media that has not been uploaded to Drive."""
        uploaded = {
            row[0]
            for row in self.connection.execute(
                "SELECT relative_path FROM drive_media_uploads"
            )
        }
        pending = {}
        rows = self.connection.execute(
            "SELECT payload FROM messages WHERE chat_id = ? ORDER BY message_id",
            (self.chat_id,),
        )
        for (payload,) in rows:
            message = json.loads(payload)
            for field in ("photo", "file"):
                relative = message.get(field)
                if not relative or relative in uploaded:
                    continue
                path = (self.data_dir / relative).resolve()
                if not path.is_relative_to(self.data_dir.resolve()):
                    raise ArchiveError(
                        f"Unsafe media path for message {message.get('id', '?')}"
                    )
                if path.is_file() and path.stat().st_size:
                    pending[relative] = path
        return list(pending.items())

    def mark_drive_media_uploaded(self, relative_path: str, drive_file_id: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO drive_media_uploads (relative_path, drive_file_id)
                VALUES (?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    drive_file_id = excluded.drive_file_id,
                    uploaded_at = CURRENT_TIMESTAMP
                """,
                (relative_path, drive_file_id),
            )

    def write_json_export(self) -> Path:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".chat_export-", suffix=".json", dir=self.data_dir
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
                destination.write("{\n")
                for key, value in (
                    ("name", self.chat_name),
                    ("type", "personal_chat"),
                    ("id", self.chat_id),
                ):
                    destination.write(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},\n")
                destination.write('  "messages": [\n')
                rows = self.connection.execute(
                    "SELECT payload FROM messages WHERE chat_id = ? ORDER BY message_id",
                    (self.chat_id,),
                )
                first = True
                for (payload,) in rows:
                    if not first:
                        destination.write(",\n")
                    destination.write("    ")
                    destination.write(payload)
                    first = False
                destination.write("\n  ]\n}\n")
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary_name, self.export_path)
            _sync_directory(self.data_dir)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return self.export_path

    def load_cleanup_state(self) -> tuple[int | None, int | None, float | None]:
        row = self.connection.execute(
            "SELECT last_incoming_id, pending_id, deadline FROM cleanup_state WHERE chat_id = ?",
            (self.chat_id,),
        ).fetchone()
        return row if row else (None, None, None)

    def save_cleanup_state(
        self, last_incoming_id: int | None, pending_id: int | None, deadline: float | None
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO cleanup_state (chat_id, last_incoming_id, pending_id, deadline)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    last_incoming_id = excluded.last_incoming_id,
                    pending_id = excluded.pending_id,
                    deadline = excluded.deadline
                """,
                (self.chat_id, last_incoming_id, pending_id, deadline),
            )

    def log_deletion(
        self, reason: str, message_count: int, status: str, detail: str | None = None
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO deletion_log (chat_id, reason, message_count, status, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.chat_id, reason, message_count, status, detail),
            )

    def messages_for_day(self, diary_date: date, timezone_name: str) -> list[dict]:
        """Return archived messages whose Telegram timestamp falls on local date."""
        local_zone = ZoneInfo(timezone_name)
        result = []
        rows = self.connection.execute(
            "SELECT payload FROM messages WHERE chat_id = ? ORDER BY message_id",
            (self.chat_id,),
        )
        for (payload,) in rows:
            message = json.loads(payload)
            raw_date = message.get("date")
            if not raw_date:
                continue
            try:
                parsed = datetime.fromisoformat(raw_date)
            except ValueError:
                continue
            # Existing exports stored dates without an offset; Telethon supplies UTC.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed.astimezone(local_zone).date() == diary_date:
                result.append(message)
        return result

    def diary_status(self, diary_date: date) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM diary_runs WHERE diary_date = ?",
            (diary_date.isoformat(),),
        ).fetchone()
        return row[0] if row else None

    def next_diary_date(self, due_date: date) -> date | None:
        """Return a failed date or the day after the last completed run.

        On a fresh archive, begin with yesterday rather than backfilling all
        historical conversation dates without an explicit starting point.
        """
        last_completed = self.connection.execute(
            "SELECT MAX(diary_date) FROM diary_runs WHERE status = 'completed' AND diary_date <= ?",
            (due_date.isoformat(),),
        ).fetchone()[0]
        oldest_pending = self.connection.execute(
            "SELECT MIN(diary_date) FROM diary_runs WHERE status != 'completed' AND diary_date <= ?",
            (due_date.isoformat(),),
        ).fetchone()[0]
        candidates = []
        if last_completed:
            candidates.append(date.fromisoformat(last_completed) + timedelta(days=1))
        if oldest_pending:
            candidates.append(date.fromisoformat(oldest_pending))
        if not candidates:
            return due_date
        next_date = min(candidates)
        return next_date if next_date <= due_date else None

    def record_diary_run(
        self,
        diary_date: date,
        status: str,
        notion_page_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO diary_runs (diary_date, status, notion_page_id, detail)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(diary_date) DO UPDATE SET
                    attempted_at = CURRENT_TIMESTAMP,
                    status = excluded.status,
                    notion_page_id = excluded.notion_page_id,
                    detail = excluded.detail
                """,
                (diary_date.isoformat(), status, notion_page_id, detail),
            )
