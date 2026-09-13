# Translations

Each file here is one language of the bot: `en.json`, `uk.json`, … The bot uses the one set in `.env`:

```
BOT_LANGUAGE=uk
```

`en.json` is the reference. If a key is missing or broken in another file, the bot shows the English text for that key and logs an `i18n:` warning at startup.

## Add a language

1. Translate `en.json` (by hand or with the prompt below) and save it as `<code>.json`, e.g. `it.json`.
2. Set `BOT_LANGUAGE=it` in `.env` and restart the bot.
3. Check the startup log for `i18n:` warnings.

## Rules

- Translate only the values. Keep the keys and structure.
- `{name}`, `{link}`, `{time_left}`, … are filled in by the bot. Keep each one, spelled exactly the same.
- `{wave}`, `{check}`, `{trophy}`, … are emoji. Move or drop them as you like.
- `<b>…</b>` is bold, `<i>…</i>` is italic. No other HTML.
- Don't translate commands: `/start`, `/time boundary`, …
- Keep `\n` line breaks.
- Pop-up texts must stay under 200 characters: keys ending in `_alert`, `war.no_players_in_db`, `access.not_registered`, `access.join_group_hint`, `api.*`, `race.load_failed`.
- After changing `menu.*`, users get the new buttons when they send /start again.

## Prompt for ChatGPT

```
Translate the values of this JSON from English to <LANGUAGE>. Return only valid JSON with the same keys and structure.
Rules: keep every {placeholder} exactly as is; keep <b></b> and <i></i> tags; keep \n line breaks;
don't translate Telegram commands like /start or /time boundary; keep texts short and friendly —
this is a Telegram bot for a Clash Royale clan.

<paste en.json here>
```
