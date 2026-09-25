"""Google Drive API adapter for private Telegram media backups."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
_APP_PROPERTY_KEY = "couplebot_media_key"


class GoogleDriveMediaWriter:
    def __init__(self, service, folder_name: str):
        self.service = service
        self.folder_id = self._ensure_folder(folder_name)

    @classmethod
    def from_token_file(cls, token_file: Path, folder_name: str):
        token_file = Path(token_file)
        if not token_file.is_file():
            raise RuntimeError(
                "Google Drive не авторизован. Выполни: "
                "python -m couplebot.cli.google_drive_auth"
            )

        credentials = Credentials.from_authorized_user_file(
            str(token_file), [DRIVE_FILE_SCOPE]
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(credentials.to_json(), encoding="utf-8")
        if not credentials.valid:
            raise RuntimeError(
                "Токен Google Drive недействителен. Повтори "
                "python -m couplebot.cli.google_drive_auth"
            )
        return cls(
            build("drive", "v3", credentials=credentials, cache_discovery=False),
            folder_name,
        )

    def _ensure_folder(self, folder_name: str) -> str:
        escaped_name = folder_name.replace("\\", "\\\\").replace("'", "\\'")
        response = (
            self.service.files()
            .list(
                q=(
                    "mimeType='application/vnd.google-apps.folder' and "
                    f"name='{escaped_name}' and trashed=false"
                ),
                spaces="drive",
                fields="files(id,name)",
                pageSize=100,
            )
            .execute()
        )
        folders = response.get("files", [])
        if folders:
            return folders[0]["id"]
        folder = (
            self.service.files()
            .create(
                body={
                    "name": folder_name,
                    "mimeType": "application/vnd.google-apps.folder",
                },
                fields="id",
            )
            .execute()
        )
        return folder["id"]

    def upload_media(self, path: Path, relative_path: str) -> str:
        marker = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
        escaped_marker = marker.replace("'", "\\'")
        response = (
            self.service.files()
            .list(
                q=(
                    f"'{self.folder_id}' in parents and "
                    f"appProperties has {{ key='{_APP_PROPERTY_KEY}' "
                    f"and value='{escaped_marker}' }} and trashed=false"
                ),
                spaces="drive",
                fields="files(id)",
                pageSize=1,
            )
            .execute()
        )
        matches = response.get("files", [])
        if matches:
            return matches[0]["id"]

        path = Path(path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        request = self.service.files().create(
            body={
                "name": path.name,
                "parents": [self.folder_id],
                "appProperties": {_APP_PROPERTY_KEY: marker},
            },
            media_body=MediaFileUpload(
                str(path), mimetype=mime_type, chunksize=8 * 1024 * 1024, resumable=True
            ),
            fields="id",
        )
        result = None
        while result is None:
            _, result = request.next_chunk(num_retries=5)
        return result["id"]
