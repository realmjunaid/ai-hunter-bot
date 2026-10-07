# Ai Hunter

Discord bot with two watches:

1. **X watch** (hourly): 37 X accounts → new **free AI model** posts
   forwarded to `CHANNEL_ID` as rich embeds.
2. **Provider watch** (every `POLL_INTERVAL_SECONDS`): OpenRouter +
   OpenCode Zen free-model add/remove alerts → `ALERT_CHANNEL_ID`.
   Slash commands: `/orfm` `/ocfm` `/ping`.

## Setup (any host)

1. `pip install -r requirements.txt`
2. `cp .env.example .env` → fill `DISCORD_TOKEN`, `CHANNEL_ID`
   (Discord Developer Portal → Bot → token; enable Message Content intent
   not needed — only send permission in the channel)
3. Test without posting: `DRY_RUN=1 CHANNEL_ID=123 python bot.py`
4. Run: `python bot.py` (checks every hour)

## Docker

```bash
docker build -t ai-hunter .
docker run -d --restart unless-stopped --env-file .env ai-hunter
```

## Config

- `accounts.json` — watched X handles
- `keywords.json` — `require_all` + `any_of` match lists
- `RSSHUB_BASE` — feed backend (default public instance; point to your own
  RSSHub if public ones rate-limit you). `RSSHUB_FALLBACKS` = comma list.
- State: `seen.db` (auto-pruned after 30 days)
