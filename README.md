# telegram-chat-remover

Monitors a Telegram contact and automatically exports the chat to a JSON file (Telegram-compatible format), then deletes all messages when they go offline.

## Features

- Exports full chat history to a structured JSON (mirrors Telegram's own export format)
- Captures text entities (bold, italic, code, links, mentions)
- Handles photos, stickers, voice messages, and video files
- Deletes all messages from both sides (`revoke=True`) after export
- Triggers automatically when the target user goes offline

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
```

Get `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org) → API development tools.

**5. Run**
```bash
python main.py
```

On first run, Telethon will ask for your phone number and a verification code to create a `session.session` file.

## Output

Each export is saved as `chat_YYYYMMDD_HHMMSS.json` in the project root. The format matches Telegram Desktop's JSON export structure so it can be used with any compatible viewer.

## Notes

- You can only delete your own messages for other users. `revoke=True` attempts to delete for both sides, but the other person's messages can only be removed from your view in private chats where Telegram allows it.
- The session file is excluded from git — keep it secure.
- Never commit `.env`.
