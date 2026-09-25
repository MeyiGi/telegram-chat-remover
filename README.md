# telegram-chat-remover

Monitors one Telegram conversation, archives it locally, and deletes its messages after you read the latest incoming message and a 30-minute grace period passes. If the contact comes online or sends another message, the pending deletion is cancelled.

The code is organized as independent automations under `couplebot/features/`, with Telegram, Groq, and Notion adapters under `couplebot/integrations/`. See [the architecture](docs/architecture.md) and [the new-feature checklist](docs/new-feature.md) before adding another automation.

## Features

- Stores messages in `data/archive.sqlite3` and writes a Telegram-style JSON export atomically
- Captures text entities (bold, italic, code, links, mentions)
- Downloads photos, stickers, voice messages, videos, and other attached files to `data/media/`
- Supports `/stats` and `/statistics` commands in the chat to refresh `data/chat_export.json` and show extended chat statistics from the export
- Checks that the live messages and attachments are archived before attempting deletion (`revoke=True`)
- Waits until you read the latest incoming message
- Deletes the archived snapshot after a 30-minute grace period, unless the contact comes online
- Resets the pending deletion state when a newer incoming message arrives
- Persists the pending timer across restarts; an already-expired timer is cancelled at startup
- Creates a daily Notion diary at 05:00 using a Groq summary of the previous day's Telegram messages
- Optionally backs up Telegram photos, videos, voice messages, stickers, and files to Google Drive before deletion

## Setup

**1. Clone and enter the project**
```bash
git clone <repo-url>
cd telegram-chat-remover
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv
source venv/bin/activate.fish   # fish shell
# or: source venv/bin/activate  # bash/zsh
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure credentials**

Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

```env
API_ID=your_api_id
API_HASH=your_api_hash
GIRLFRIEND_USERNAME=@username_or_phone
MY_PHONE=your_telegram_phone
DELETE_DRY_RUN=1
DIARY_ENABLED=1
DIARY_TIMEZONE=Asia/Bishkek
DIARY_HOUR=5
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
NOTION_TOKEN=your_notion_integration_token
NOTION_DIARY_PARENT_PAGE_ID=your_notion_parent_page_id
```

Get `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org) → API development tools.

**5. Run**
```bash
python -m couplebot
```

For a separate interactive login, run `python -m couplebot.cli.auth` first. The older `python main.py` and `python auth.py` commands still work. Telethon stores the session under the name set by `TELEGRAM_SESSION` (default: `karlis_listener.session`).

## Output

The SQLite archive is stored in `data/archive.sqlite3`, downloaded attachments in `data/media/`, and a rolling JSON export in `data/chat_export.json`. An existing JSON export is imported into SQLite on first startup. Previously deleted attachments that were never downloaded cannot be recovered by this migration.

When you send `/stats` or `/statistics` in the monitored chat, the app first syncs the latest messages into `data/chat_export.json` and then builds an extended stats report from that file.

The example configuration starts in preview mode: when deletion would be due, the app archives the chat and records a `preview` entry in SQLite without deleting messages. Set `DELETE_DRY_RUN=0` after checking the export and attachments. A preview clears that pending timer; the next deletion needs a new incoming message and read event.

At 05:00 in `DIARY_TIMEZONE`, the app syncs the conversation, sends the previous local calendar day's text to Groq, and writes the result into `Дневник → год → месяц → день` in Notion. Missing year, month, or day pages are created automatically; existing pages are reused, and an automatic entry is marked to avoid adding it twice. Failed dates are retried and missed dates after the last completed entry are processed in order. On the first run, the diary starts with the previous day. Share the Notion root page with the integration and keep both API tokens only in `.env`.

### Google Drive media backup

To back up archived Telegram media, enable the Google Drive API in Google Cloud Console and create an OAuth client of type **Desktop app**. Save the downloaded JSON as `credentials/google-drive-client.json`, add `GOOGLE_DRIVE_ENABLED=1` to `.env`, then run:

```bash
python -m couplebot.cli.google_drive_auth
```

Authorize the Google account that owns the Drive. On the next app start, existing local archive media and new photos, videos, voice messages, stickers, and other files are uploaded into the `CoupleBot Media` folder. The app uses resumable uploads and records completed uploads in SQLite, so retries do not create duplicates. Missing local attachments cannot be recovered from Google Drive; they must still exist in the Telegram archive.

The saved OAuth token is stored under `data/` and is excluded from git. Google may expire refresh tokens after 7 days while an external OAuth app remains in Testing status; for uninterrupted automation, publish the OAuth app or reauthorize when Google expires the token.

## Notes

- `revoke=True` requests deletion for both sides where Telegram permits it. The deletion attempts and results are recorded in SQLite.
- Detecting that the contact "entered the chat" relies on Telegram read receipts for your outgoing messages in that dialog.
- The session file is excluded from git — keep it secure.
- Never commit `.env`.
- The entire `data/` directory is ignored by git because it contains private conversation data.
