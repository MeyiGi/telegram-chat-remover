"""Authorize the app to upload files into its private Drive folder."""

from __future__ import annotations

from google_auth_oauthlib.flow import InstalledAppFlow

from couplebot.config import GoogleDriveAuthConfig
from couplebot.integrations.google_drive import DRIVE_FILE_SCOPE


def main() -> None:
    config = GoogleDriveAuthConfig.from_env()
    if not config.client_secrets_file.is_file():
        raise FileNotFoundError(
            "OAuth client JSON не найден: "
            f"{config.client_secrets_file}. Скачай OAuth client типа Desktop app "
            "из Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.client_secrets_file), [DRIVE_FILE_SCOPE]
    )
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    config.token_file.parent.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Google Drive подключён. Токен сохранён в {config.token_file}.")


if __name__ == "__main__":
    main()
