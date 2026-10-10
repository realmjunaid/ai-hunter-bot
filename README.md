# 🏹 Ai Hunter

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.4%2B-blurple.svg)](https://discordpy.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Free & Open Source](https://img.shields.io/badge/free-open%20source-brightgreen.svg)](LICENSE)

**Ai Hunter is a free, open-source Discord bot that watches the AI world for you.**

It tracks **38 X (Twitter) accounts** for free-AI-model announcements every hour, and polls **OpenRouter, OpenCode Zen, and Infron** every few minutes for free-model additions and removals — posting rich Discord embeds the moment something changes. It also answers slash commands so anyone on your server can list current free models on demand.

Free for everyone — use it, fork it, self-host it. 💚

---

## ✨ Features

| Watch | What it does | Cadence |
|---|---|---|
| 🐦 **X watch** | Forwards new free-AI-model posts from 38 curated accounts to `CHANNEL_ID` | Hourly |
| 🔌 **OpenRouter** | Alerts on free-model **added / removed** → `ALERT_CHANNEL_ID` | Every 30 min |
| ⚡ **OpenCode Zen** | Alerts on free-model **added / removed** → `ALERT_CHANNEL_ID` | Every 30 min |
| 🛰️ **Infron** | Alerts on free-model **added / removed** → `ALERT_CHANNEL_ID` | Every 30 min |

**Slash commands** (available to everyone on the server):

- `/orfm` — list all current OpenRouter free models
- `/ocfm` — list all current OpenCode Zen free models
- `/infm` — list all current Infron free models
- `/xpost` — check X accounts for the last 24h right now (on-demand)
- `/ping` — check the bot is alive

**Reliability built in:** concurrent fetching, response caching, retry with backoff, duplicate suppression (`seen.db`, auto-pruned after 30 days), graceful degradation when a feed or API is down, and a `DRY_RUN` mode for safe testing.

---

## 🚀 Quickstart

**Requirements:** Python 3.12+, a Discord bot token ([create one here](https://discord.com/developers/applications) — only the **Send Messages** permission is needed; no privileged intents).

```bash
git clone https://github.com/realmjunaid/ai-hunter-bot.git
cd ai-hunter-bot
pip install -r requirements.txt
cp .env.example .env   # then fill in your values (see below)
python bot.py
```

**Test without posting anything:**

```bash
DRY_RUN=1 CHANNEL_ID=123 python bot.py
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and set:

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token from the Discord Developer Portal |
| `CHANNEL_ID` | ✅ | Channel for X-watch post embeds |
| `ALERT_CHANNEL_ID` | ➖ | Channel for provider add/remove alerts (same as above or different; `0` = provider watch off) |
| `POLL_INTERVAL_SECONDS` | ➖ | Provider poll interval, minimum 60 (default `1800` = 30 min; X watch stays hourly) |
| `RSSHUB_BASE` | ➖ | RSS feed backend (default public instance; point to your own RSSHub if rate-limited) |
| `RSSHUB_FALLBACKS` | ➖ | Comma-separated fallback feed backends |
| `OPENROUTER_API_KEY` | ➖ | Optional — raises OpenRouter rate limits |
| `DRY_RUN` | ➖ | `1` = fetch and print only, never post or log in |

**Watch lists** (edit the JSON, restart the bot):

- `accounts.json` — X handles to watch
- `keywords.json` — `require_all` (every word must match) + `any_of` (at least one must match)

**Local state** (auto-created, never commit): `seen.db` (posted tweets), `*_history.json` / `*_known.json` (provider model ids).

---

## 🧪 Tests

```bash
python test_all.py
```

One file, four sections (filter/store, providers, fix-pass, regressions). It must print `ALL TESTS PASS` with exit code `0`.

---

## 🗂️ Project structure

```
bot.py              # Discord wiring: loops, slash commands, entrypoint
providers.py        # OpenRouter / OpenCode Zen / Infron fetch, diff, alerts
xwatch.py           # X watch: RSS fetching, keyword filter, seen-store (WAL, auto-pruned)
config.py           # env/.env loading with friendly ConfigError messages
test_all.py         # all tests (filter, providers, fix-pass, regressions)
accounts.json       # watched X handles
keywords.json       # match lists
requirements.txt    # discord.py, aiohttp, python-dotenv, feedparser
```

---

## 🤝 Contributing

Contributions are welcome! Fork the repo, create a branch, make sure all four test suites pass, and open a pull request. Bug reports and feature ideas via [GitHub Issues](https://github.com/realmjunaid/ai-hunter-bot/issues).

---

## 📄 License

MIT — see [LICENSE](LICENSE). Free for personal and commercial use.

## ⚠️ Disclaimer

X-post monitoring depends on third-party RSS backends (RSSHub-compatible). If a public instance rate-limits you, self-host RSSHub and set `RSSHUB_BASE`. This project is not affiliated with Discord, X, OpenRouter, OpenCode, or Infron.
