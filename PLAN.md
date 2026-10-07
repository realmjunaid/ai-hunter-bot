# Ai Hunter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Ai Hunter Discord bot per DESIGN.md.

**Architecture:** Single Python service: RSSHub fetch → keyword filter → sqlite dedupe → Discord embed, on an hourly `tasks.loop`. Host-agnostic (env config + Dockerfile).

**Tech Stack:** Python 3.11+, discord.py 2.x, aiohttp, stdlib sqlite3.

**Spec:** `E:\Bot\Ai Hunter\DESIGN.md`

## Global Constraints
- No paid APIs, no X login.
- Secrets only via env (`.env`, never committed).
- DRY_RUN=1 must print embeds instead of posting.

## Review Focus
- RSSHub returns non-RSS/HTML error page → fetcher must not crash, tries next instance.
- Tweet text with Discord markdown (e.g. `_`, `*`) breaking embed layout → escape or truncate safely.
- Timezone-naive vs aware datetimes in loop scheduling → use UTC throughout.
- Empty feed for an account (suspended/renamed handle) → log + skip, no crash.
- sqlite locked on unclean shutdown → WAL mode + short timeouts.

---

### Task 1: Project skeleton + config

**Files:**
- Create: `E:\Bot\Ai Hunter\requirements.txt` (`discord.py>=2.4`, `aiohttp>=3.9`, `python-dotenv`, `feedparser`)
- Create: `E:\Bot\Ai Hunter\.env.example` (`DISCORD_TOKEN=`, `CHANNEL_ID=`, `RSSHUB_BASE=` (optional), `RSSHUB_FALLBACKS=` (optional), `DRY_RUN=0`)
- Create: `E:\Bot\Ai Hunter\accounts.json` (12 handles: OpenRouter, InfronAI, aimlapi, cerebras, opencode, testingcatalog, rayycfu, DeRonin_, sairahul1, StudentOffersHQ, cline, JulianGoldieSEO)
- Create: `E:\Bot\Ai Hunter\keywords.json` (`require_all`: ["free"], `any_of`: ["model","api","llm","inference","openrouter","endpoint",":free","release"])
- Create: `E:\Bot\Ai Hunter\config.py` — `load() -> Config` dataclass (token, channel_id:int, rsshub_base, fallbacks:list, dry_run:bool); raises `ConfigError` on missing token/channel.

**Interfaces:**
- Produces: `config.load()`, `Config`, `ConfigError` (used by Task 4).

- [ ] **Step 1: Create the 5 files** with the exact names/keys above.
- [ ] **Step 2: Verify** — `python -c "import config; print(config.load())"` with a temp `.env` fails cleanly on missing vars (expect `ConfigError`), then delete temp `.env`. Expected: error message, no traceback leak of values.

### Task 2: Fetcher (RSSHub)

**Files:**
- Create: `E:\Bot\Ai Hunter\fetcher.py` — `fetch_user_tweets(handle, session, base, timeout=20) -> list[Tweet]`; `Tweet` = dataclass(handle, id, text, url, created_utc). Tries `base` then each fallback (`{base}/twitter/user/{handle}`); on 429/5xx/non-RSS, next instance; all fail → returns `[]`.

**Interfaces:**
- Consumes: `Config.rsshub_base`, `Config.fallbacks` (Task 1).
- Produces: `fetch_user_tweets`, `Tweet` (used by Task 4).

- [ ] **Step 1: Implement** `fetch_user_tweets` + `Tweet` in `fetcher.py` (feedparser for RSS).
- [ ] **Step 2: Verify live** — fetch 1 handle, print count + first id. Expected: `>=0` items, no exception (empty OK if instance flaky; try fallback).

### Task 3: Filter + store

**Files:**
- Create: `E:\Bot\Ai Hunter\filter.py` — `is_match(text, keywords) -> tuple[bool, list[str]]` (case-insensitive; skips `RT @` and `@reply` prefixes).
- Create: `E:\Bot\Ai Hunter\store.py` — `mark_seen(db, tweet_id)`, `is_seen(db, tweet_id) -> bool`, `prune(db, days=30)`; sqlite WAL mode.
- Create: `E:\Bot\Ai Hunter\test_filter.py` — asserts: match on "FREE DeepSeek V4.1 API", no match on "paid model launch", no match on "RT @x free model", keyword list returned.

**Interfaces:**
- Produces: `is_match`, `mark_seen/is_seen/prune` (used by Task 4).

- [ ] **Step 1: Write `test_filter.py`** with the 4 assertions above.
- [ ] **Step 2: Run** `python test_filter.py` — expect FAIL (no module).
- [ ] **Step 3: Implement** `filter.py` + `store.py`.
- [ ] **Step 4: Re-run** — expect PASS.

### Task 4: Bot + embed + Dockerfile + README

**Files:**
- Create: `E:\Bot\Ai Hunter\bot.py` — `build_embed(tweet, keywords) -> discord.Embed` (title=`{name} (@handle)`, url=profile link, desc=text+`\n\n[tweet link]`, field=matched keywords, timestamp, green color); hourly `tasks.loop(check)`; `DRY_RUN=1` prints instead of sending; send retry 3x, unmarked IDs retried next hour.
- Create: `E:\Bot\Ai Hunter\Dockerfile` (`python:3.12-slim`, copy, `pip install -r requirements.txt`, `CMD ["python","bot.py"]`), `E:\Bot\Ai Hunter\.dockerignore` (`.env`, `seen.db`, `__pycache__`).
- Create: `E:\Bot\Ai Hunter\README.md` — hosting guide (env vars, docker run, hourly loop, DRY_RUN test).

**Interfaces:**
- Consumes: all Tasks 1–3.

- [ ] **Step 1: Implement** `bot.py`, `Dockerfile`, `.dockerignore`, `README.md`.
- [ ] **Step 2: Verify** — `python -m py_compile *.py` clean; `DRY_RUN=1` with stub data prints an embed-shaped output without needing a token. Expected: no exceptions.
