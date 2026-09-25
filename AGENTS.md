@/home/meyigi/.codex/RTK.md

# Project guide

This is a private, long-lived automation project for one Telegram conversation and related personal records. Read `docs/architecture.md` before changing runtime behavior.

## Navigation

- Check CodeGraph status before editing unfamiliar code. If this repository is not indexed, say that `codegraph init` is needed and inspect the files normally.
- `couplebot/cli/` owns the run and login entry points; `main.py` and `auth.py` are legacy launchers. `couplebot/app.py` wires the running application.
- `couplebot/features/<name>/` owns one automation. Keep its business rules and scheduled job together.
- `couplebot/integrations/` owns Telegram, Groq, Notion, and future external API calls.
- `couplebot/storage/` owns SQLite and local files. Never make a feature depend on another feature's private tables.
- `couplebot/config.py` is the only place that reads environment variables.

## Adding an automation

1. Define its trigger, input, output, idempotency key, retry policy, and owner of persisted state in `docs/architecture.md`.
2. Put the workflow in its own `features/<name>/` package. Inject clients and storage through its constructor or function arguments.
3. Put external API details in `integrations/`; keep tokens out of feature code.
4. Persist source Telegram messages before performing actions that depend on them. Make external writes safe to retry and record completion locally.
5. Add focused tests with fake integrations for rules and failure recovery. Avoid live Telegram, Groq, or Notion calls in automated tests.
6. Update `.env.example` and README when configuration or user behavior changes.

## Invariants

- Never delete Telegram messages until the complete archive and media verification succeeds. Keep preview mode available.
- Treat Telegram message IDs as unique only within a chat. Store timestamps in UTC and convert to `DIARY_TIMEZONE` for day-based jobs.
- Do not print tokens, raw private conversation text, or media paths in normal logs. Keep `.env`, session files, and `data/` out of Git.
- Keep feature modules importable without network access or reading `.env`. Only the composition root starts clients and jobs.
- Preserve existing archive and `diary_runs` data when evolving the SQLite schema. Prefer additive migrations.
- Keep `python main.py` and `python auth.py` working as thin launchers. Import implementation modules from `couplebot`, not from those launchers.
