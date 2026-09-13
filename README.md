<div align="center">

# Clash Royale Clan Telegram Bot

**Runs your Clash Royale clan's Telegram chat.** Players join by their in-game tag, the bot tracks war decks,
pings whoever hasn't played and shows river race stats — so clan leaders stop chasing people by hand.

[![CI](https://github.com/Mesh4ek/clash-royale-clan-tg-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Mesh4ek/clash-royale-clan-tg-bot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-3776AB?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-22-26A5E4?logo=telegram&logoColor=white)
![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)

</div>

<!--
Screenshots: put the images in docs/screenshots/ and uncomment this block.

<p align="center">
  <img src="docs/screenshots/war.png" width="250" alt="Players who haven't used their war decks, with tabs for earlier days">
  <img src="docs/screenshots/race.png" width="250" alt="River race standings">
  <img src="docs/screenshots/reminder.png" width="250" alt="Reminder in the clan chat">
</p>
-->

## Features

- **Verified clan chat.** Players register with their Clash Royale tag; the bot checks they are in the clan and sends a personal invite link. Join requests from anyone else are declined. Members get their in-game nickname as a title in the group, and the bot posts who joined or left.
- **War deck tracking.** `/war` shows who still has decks to play today: registered players with a link to their Telegram profile, then clan members who aren't in the chat. Tabs for earlier days of the current war show who skipped their decks.
- **Reminders without spam.** Before the war day ends, the bot pings everyone with unused decks. The “Notify everyone” button lets members ping the group themselves, but only in the last hours of the day.
- **River race stats.** `/race` lists every clan in the race with decks used, medals, average medals per deck, a projection for the day and boat progress, plus results by day and the last five wars.
- **Clan info.** `/rank` shows the clan's place in its region's ranking; `/missing` lists clan members who haven't joined the chat.
- **Admin tools.** Hidden commands in a private chat with the bot: change the war schedule without a restart, read logs, export players, remove a registration (and the player from the chat), and get a weekly database backup.
- **Localization.** Every chat text lives in a JSON file. English and Ukrainian are included; adding a language is one file.
- **Production-ready setup.** Read-only Docker container, SQLite in a volume, CI with lint and image build, and a deploy workflow to your server through GHCR.

## How it works

During a war the bot reads the clan's river race from the official Clash Royale API, and every 30 minutes it saves how many decks each member has used. That is how it can show who skipped their decks on earlier days, which the API itself doesn't keep.

## Quick start

You need Python 3.13+ or Docker, a Telegram account and a Clash Royale account.

### 1. Create the Telegram bot

1. Open [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Enter a display name for the bot, then a username that ends in `bot` (for example `my_clan_bot`).
3. BotFather replies with a token like `123456789:AA…`. This is `TELEGRAM_BOT_TOKEN`. Anyone with the token controls the bot, so keep it secret. If it leaks, send `/revoke` to BotFather to get a new one.

### 2. Get a Clash Royale API key

1. Register or sign in at [developer.clashroyale.com](https://developer.clashroyale.com/).
2. Open **My Account** and click **Create New Key**.
3. Enter a name and description. Under **Allowed IP Addresses**, enter the public IP of the machine that will run the bot. A key works only from the IPs you list, so if that IP changes, create a new key.
4. Create the key and copy its token. This is `CLASH_API_TOKEN`.
5. In the game, open your clan's profile and copy the tag under its name (for example `#ABC123`). This is `CLAN_TAG`.

### 3. Create the clan group

1. In Telegram, create a new group and add your bot as a member.
2. Keep the group private: don't give it a public link or @username. In a public group people can join directly without registering, and Telegram ignores the bot's personal join links.

### 4. Make the bot an admin

In the group settings, open **Administrators**, add the bot and turn on only these rights:

- **Invite users via link**: personal invite links and approving join requests
- **Ban users**: removing players with `/unregister`
- **Add new admins**: in-game nicknames as member titles (the bot gives members a title-only admin role)

All other rights can stay off. Being an admin is also what lets the bot see who joins and leaves the group.

### 5. Find the group ID and your Telegram ID

Do this before you start the bot: a running bot takes these updates first.

1. Send any message in the group, and send any message to your bot in a private chat.
2. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser, with your bot token instead of `<TOKEN>`.
3. In the response, find:
   - the group's `"chat": {"id": -100…}`. This is `TELEGRAM_GROUP_ID`. A group's ID changes when Telegram upgrades it to a supergroup, so take it after step 4 and check that it starts with `-100`.
   - your own `"from": {"id": …}` from the private chat. Put it in `LOGS_ALLOWED_TG_IDS` to get the admin commands.

### 6. Configure the bot

```bash
git clone https://github.com/Mesh4ek/clash-royale-clan-tg-bot.git
cd clash-royale-clan-tg-bot
cp .env.example .env
```

Fill in `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_GROUP_ID=-1001234567890
CLASH_API_TOKEN=your_clash_royale_api_token
CLAN_TAG=#ABC123
LOGS_ALLOWED_TG_IDS=123456789
BOT_LANGUAGE=en
```

Everything else is optional, see [Configuration](#configuration).

### 7. Run the bot

With Docker:

```bash
docker compose up -d --build
```

Or locally:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### 8. Check that it works

1. Open your bot in Telegram, send `/start` and then your player tag. The bot checks that you're in the clan and sends you a personal link to the group.
2. Join the group with that link. The bot approves the request, welcomes you and sets your in-game nickname as your title.
3. Send `/war` or `/race` to the bot in the private chat.
4. As an admin, send `/admin` to see the admin commands. Then set the time the war day actually ends in your clan with `/time auto H M` (UTC), see [War schedule](#war-schedule).

## Configuration

Settings are read from `.env`. Only the first four are required.

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | — | Bot token from @BotFather |
| `TELEGRAM_GROUP_ID` | — | ID of the clan's Telegram group (`-100…`) |
| `CLASH_API_TOKEN` | — | Clash Royale API key |
| `CLAN_TAG` | — | Clan tag, e.g. `#ABC123` |
| `LOGS_ALLOWED_TG_IDS` | empty | Admin Telegram user IDs, comma-separated. The first one gets the weekly backup |
| `BOT_LANGUAGE` | `en` | Language file from `locales/` (`en`, `uk`, …) |
| `CLASH_LOCATION_ID` | clan's region | Region used by `/rank` |
| `WAR_DAY_END_UTC`, `WAR_DAY_END_MINUTE` | `9`, `30` | When a war day ends (UTC). Change later with `/time` |
| `WAR_REMINDER_UTC`, `WAR_REMINDER_MINUTE` | `9`, `0` | When the automatic reminder is sent (UTC) |
| `WEEKLY_DATA_BACKUP` | `1` | Set `0` to turn off the Thursday backup message |
| `DATABASE_PATH` | `database/database.db` | SQLite file; the war schedule is saved next to it |
| `RIVER_RACE_DECKS_PER_DAY` | `4` | War decks per player per day |
| `REQUEST_TIMEOUT_SECONDS` | `15` | Timeout for Clash Royale API calls |
| `TELEGRAM_PROXY` | — | HTTP proxy for Telegram (`HTTPS_PROXY` also works) |
| `POLL_INTERVAL` | `0` | Seconds between Telegram update polls |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO` or `WARNING` |

## Commands

Commands work in a private chat with the bot. Clan commands need a registered player who has joined the group.

| Command | What it does |
|---------|--------------|
| `/start` | Registration instructions and the menu |
| `/war` | Who hasn't used their war decks, with tabs for earlier days and a “Notify everyone” button |
| `/race` | River race standings, results by day and past wars |
| `/rank` | The clan's place in its region's ranking |
| `/missing` | Clan members who aren't in the Telegram group |

### Admin commands

Hidden from the menu and available only to `LOGS_ALLOWED_TG_IDS`.

| Command | What it does |
|---------|--------------|
| `/admin` | List of admin commands |
| `/time` | View and change the war schedule: day end, reminder time, “Notify everyone” window |
| `/logs` | Last 100 lines of the bot log |
| `/data` | Export registered players as a table |
| `/unregister` | Remove a player's registration by tag, @username or Telegram ID; removing all accounts also removes them from the group |

## War schedule

Clan wars run from Thursday to Monday. Clash Royale switches to the next war day at about the same time every day, but that time can shift by a few minutes from one season to the next. Check when the day actually changes in your clan and set it with `/time auto H M`: this sets the day end and moves the automatic reminder to 30 minutes before it.

## Localization

All texts are in [`locales/`](locales/). To add a language, translate `en.json`, save it as `<code>.json` and set `BOT_LANGUAGE`. The [translation guide](locales/README.md) has the rules and a ready-made prompt for ChatGPT. Missing or broken keys fall back to English.

## Project structure

```
main.py                  Entry point
src/
├── app.py               Startup and handler registration
├── config.py            Settings from .env
├── clash_api.py         Clash Royale API client with caching
├── database.py          SQLite: players and war deck snapshots
├── handlers/            Registration, war, race, clan and admin commands
├── jobs.py              Reminders, weekly backup, deck snapshots
├── i18n.py, markup.py   Translations and Telegram message formatting
├── river_race.py        River race parsing and stats
├── war_days.py          Decks per war day from snapshots
├── war_schedule.py      War day end and reminder times
└── reports.py, race_reports.py   Message builders
locales/                 Translations (en, uk)
tests/                   Test suite
deploy/                  Production compose file and deployment guide
```

## Development

```bash
pip install -r requirements-dev.txt
pytest
ruff check src main.py tests
```

The tests cover the war and river race logic, message formatting, translations, the war schedule and the admin and group handlers. They run without a Telegram bot or a Clash Royale API key; CI runs them on every push.

## Deployment

See the [deployment guide](deploy/README.md) for running the bot on a server with Docker, GitHub Actions and GHCR.

## License

[MIT](LICENSE)

This material is unofficial and is not endorsed by Supercell. For more information see Supercell's Fan Content Policy: www.supercell.com/fan-content-policy.
