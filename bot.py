"""Ai Hunter — hourly X watch for free-AI-model posts -> Discord embeds."""
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
import discord
from discord.ext import tasks

import config as cfgmod
import providers as pv
from xwatch import Tweet, connect, fetch_user_tweets, is_match, is_seen, mark_seen, prune

log = logging.getLogger("aihunter")
# Anchor data files to this file's directory, not the caller's cwd ("." only
# works when the process happens to start in the app folder).
BASE_DIR = Path(__file__).resolve().parent


def esc(text: str) -> str:
    return re.sub(r"([*_`~|>])", r"\\\1", text)


def build_embed(tw: Tweet, keywords: list) -> discord.Embed:
    profile = f"https://x.com/{tw.handle}"
    # Escape first, then truncate: escaping after slicing can push the
    # description past Discord's 4096-char limit on escape-heavy text.
    body = esc(tw.text)
    if len(body) > 3900:
        body = body[:3900].rstrip("\\") + "…"
    em = discord.Embed(
        title=f"{tw.handle} (@{tw.handle})",
        url=profile,
        description=f"{body}\n\n[View post]({tw.url})",
        color=0x22C55E,
        timestamp=tw.created_utc,
    )
    em.add_field(name="Matched", value=", ".join(f"`{k}`" for k in keywords) or "`free`", inline=False)
    em.set_footer(text="via Ai Hunter")
    return em


async def _fetch_handle(session, cfg, handle):
    try:
        tweets = await fetch_user_tweets(handle, session, cfg.rsshub_base, cfg.fallbacks)
        return handle, tweets
    except Exception as e:
        log.warning("fetch %s failed: %s", handle, e)
        return handle, []


async def check_once(bot, cfg, keywords, db, accounts, max_age_hours=None) -> int:
    """Fetch every handle, post new matches. With max_age_hours set,
    tweets older than the window are skipped (for on-demand catch-ups)."""
    sent = 0
    skipped_old = 0
    now = datetime.now(timezone.utc)
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(5)

        async def _bounded(handle):
            async with sem:
                return await _fetch_handle(session, cfg, handle)

        # I/O-bound fetches run concurrently; posting stays sequential
        # below to keep channel rate limits and send order stable.
        results = await asyncio.gather(*(_bounded(h) for h in accounts))
        for handle, tweets in results:
            if not tweets:
                log.info("no items for %s this round", handle)
                continue
            if max_age_hours is not None:
                fresh = []
                for tw in tweets:
                    created = tw.created_utc
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age_h = (now - created).total_seconds() / 3600
                    if age_h <= max_age_hours:
                        fresh.append(tw)
                    else:
                        skipped_old += 1
                tweets = fresh
                if not tweets:
                    log.info("no fresh items for %s this round (window %dh)", handle, max_age_hours)
                    continue
            # Oldest first so a catch-up round reads chronologically.
            tweets = sorted(tweets, key=lambda tw: (
                tw.created_utc.replace(tzinfo=timezone.utc)
                if tw.created_utc.tzinfo is None else tw.created_utc))
            for tw in tweets:
                ok, hits = is_match(tw.text, keywords)
                if not ok or is_seen(db, tw.id):
                    continue
                em = build_embed(tw, hits)
                if cfg.dry_run:
                    print(f"--- DRY {tw.handle}/{tw.id} ---")
                    print(em.title, "|", em.url)
                    print(em.description[:200])
                    sent += 1
                    continue
                for attempt in range(3):
                    try:
                        ch = bot.get_channel(cfg.channel_id) or await bot.fetch_channel(cfg.channel_id)
                        await ch.send(embed=em)
                        mark_seen(db, tw.id)
                        sent += 1
                        break
                    except Exception as e:
                        log.warning("send failed (try %d): %s", attempt + 1, e)
                        await asyncio.sleep(5)
                await asyncio.sleep(1)
    prune(db)
    if skipped_old:
        log.info("skipped %d tweets older than window", skipped_old)
    return sent


def main():
    logging.basicConfig(level=logging.INFO)
    cfg = cfgmod.load()
    with open(BASE_DIR / "accounts.json", encoding="utf-8") as f:
        accounts = json.load(f)
    with open(BASE_DIR / "keywords.json", encoding="utf-8") as f:
        keywords = json.load(f)
    db = connect(str(BASE_DIR / "seen.db"))

    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(bot)
    pv.register_commands(tree)

    @tree.command(name="xpost", description="Check X accounts for new free-model posts right now")
    async def xpost(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        if x_lock.locked():
            e = pv.base_embed("Already Checking", pv.C_INFO)
            e.description = "An X check is already running — please wait a minute."
            await interaction.followup.send(embed=e, ephemeral=True)
            return
        async with x_lock:
            n = await check_once(bot, cfg, keywords, db, accounts, max_age_hours=24)
        e = pv.base_embed("X Check Done", pv.C_SUCCESS)
        e.description = (f"Checked {len(accounts)} accounts for the last 24 hours, "
                         f"posted {n} new.")
        await interaction.followup.send(embed=e, ephemeral=True)
    or_lock = asyncio.Lock()
    oc_lock = asyncio.Lock()
    if_lock = asyncio.Lock()
    x_lock = asyncio.Lock()
    synced = False
    seeded = False

    @tasks.loop(hours=1)
    async def hourly():
        async with x_lock:
            n = await check_once(bot, cfg, keywords, db, accounts)
        log.info("x round done, posted %d", n)

    @tasks.loop(seconds=cfg.poll_interval)
    async def poll_or():
        await pv.poll_provider(bot, cfg.alert_channel_id, "OpenRouter",
                               pv.fetch_or_free, pv.or_history, pv.or_cache, or_lock)

    @tasks.loop(seconds=cfg.poll_interval)
    async def poll_oc():
        await pv.poll_provider(bot, cfg.alert_channel_id, "OpenCode Zen",
                               pv.fetch_oc_free, pv.oc_history, pv.oc_cache, oc_lock)

    @tasks.loop(seconds=cfg.poll_interval)
    async def poll_if():
        await pv.poll_provider(bot, cfg.alert_channel_id, "Infron",
                               pv.fetch_if_free, pv.if_history, pv.if_cache, if_lock)

    @bot.event
    async def on_ready():
        nonlocal synced, seeded
        log.info("logged in as %s", bot.user)
        if not synced:
            try:
                n = await tree.sync()
                log.info("synced %d commands", len(n))
                # Only mark synced on success, otherwise a single transient
                # failure leaves the bot without slash commands for its lifetime.
                synced = True
            except Exception as e:
                log.warning("tree.sync failed: %s", e)
        # Seed provider state silently so first poll doesn't spam.
        # Runs once per process (on_ready fires on every reconnect);
        # poll_provider self-seeds if a seed fetch failed transiently.
        if cfg.alert_channel_id and not seeded:
            seeded = True
            if not pv.or_history.ids:
                try:
                    pv.or_history.touch(set((await pv.fetch_or_free(force=True)).keys()))
                    pv.or_history.save()
                except Exception as e:
                    log.warning("initial OpenRouter fetch failed: %s", e)
            if not pv.oc_history.ids:
                try:
                    pv.oc_history.touch(set((await pv.fetch_oc_free(force=True)).keys()))
                    pv.oc_history.save()
                except Exception as e:
                    log.warning("initial OpenCode fetch failed: %s", e)
            if not pv.if_history.ids:
                try:
                    pv.if_history.touch(set((await pv.fetch_if_free(force=True)).keys()))
                    pv.if_history.save()
                except Exception as e:
                    log.warning("initial Infron fetch failed: %s", e)
        for loop in (hourly, poll_or, poll_oc, poll_if):
            if not loop.is_running():
                loop.start()

    if cfg.dry_run:
        print("DRY_RUN=1 — no Discord login. Feed check only.")
        n = asyncio.run(check_once(None, cfg, keywords, db, accounts))
        print(f"dry round done, would post {n}")
        return
    try:
        bot.run(cfg.token)
    finally:
        asyncio.run(pv.close_session())


if __name__ == "__main__":
    main()
