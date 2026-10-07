# Ai Hunter — Design Spec (2026-10-07)

## Intent
Python Discord bot ("Ai Hunter") hosted elsewhere by user. Polls 12 X accounts
hourly, detects new "free AI model" posts, forwards to a Discord channel as a
rich embed. No paid APIs — all free.

## Non-goals
- No X login / paid API. No tweet posting. No DM. Dashboard nei.

## Architecture (single service, stdlib + discord.py)
- `bot.py` — discord client, hourly `tasks.loop`, orchestration.
- `fetcher.py` — RSSHub feed fetch per handle. Base URL from env
  (`RSSHUB_BASE`, default public instance). Multi-instance fallback list +
  exponential backoff on 429/5xx.
- `filter.py` — keyword match: requires "free"-family word AND model/API word
  (lists in `keywords.json`, editable). Skips retweets/replies (text prefix).
- `store.py` — sqlite `seen.db`: tweet IDs already posted. Prunes >30 days.
- `accounts.json` — 12 handles from free-ai-model-x-accounts.txt.
- `.env` (from `.env.example`) — DISCORD_TOKEN, CHANNEL_ID, RSSHUB_BASE (optional).
- `Dockerfile` + `requirements.txt` + `README.md` (hosting guide).

## Data flow
loop tick → for each handle: fetch feed → new items → filter → not seen →
Discord embed → mark seen. Failures logged, loop continues.

## Embed
Title: author name + @handle (URL = profile link, clickable). Description:
tweet text (≤4000 chars, link to tweet at end). Fields: matched keywords.
Footer: via Ai Hunter. Timestamp: tweet time. Color: green.

## Error handling
- Feed fail → try next instance → else skip account this round, log.
- Discord send fail → retry 3x, then keep ID unmarked (retry next hour).
- No posts → silent (optional log).

## Testing
- `filter.py` unit check with sample tweets (no network).
- Dry-run mode: `DRY_RUN=1` prints embeds instead of posting.
- Verified: `python -m py_compile`, dry-run output reviewed.
