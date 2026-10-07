"""Ai Hunter — hourly X watch for free-AI-model posts -> Discord embeds."""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import tasks

import config as cfgmod
import providers as pv
from fetcher import Tweet, fetch_user_tweets
from filter import is_match
from store import connect, is_seen, mark_seen, prune

log = logging.getLogger("aihunter")
BASE_DIR = __file__.rsplit("\\", 1)[0] if "\\" in __file__ else "."


def esc(text: str) -> str:
    return re.sub(r"([*_`~|>])", r"\\\1", text)


def build_embed(tw: Tweet, keywords: list) -> discord.Embed:
    profile = f"https://x.com/{tw.handle}"
    body = esc(tw.text[:3500])
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


async def check_once(bot, cfg, keywords, db, accounts) -> int:
    sent = 0
    async with aiohttp.ClientSession() as session:
        for handle in accounts:
            try:
                tweets = await fetch_user_tweets(handle, session, cfg.rsshub_base, cfg.fallbacks)
            except Exception as e:
                log.warning("fetch %s failed: %s", handle, e)
                continue
            if not tweets:
                log.info("no items for %s this round", handle)
                continue
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
    return sent


def main():
    logging.basicConfig(level=logging.INFO)
    cfg = cfgmod.load()
    with open(f"{BASE_DIR}/accounts.json", encoding="utf-8") as f:
        accounts = json.load(f)
    with open(f"{BASE_DIR}/keywords.json", encoding="utf-8") as f:
        keywords = json.load(f)
    db = connect(f"{BASE_DIR}/seen.db")

    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(bot)
    pv.register_commands(tree)
    or_lock = asyncio.Lock()
    oc_lock = asyncio.Lock()
    synced = False

    @tasks.loop(hours=1)
    async def hourly():
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

    @bot.event
    async def on_ready():
        nonlocal synced
        log.info("logged in as %s", bot.user)
        if not synced:
            try:
                n = await tree.sync()
                log.info("synced %d commands", len(n))
            except Exception as e:
                log.warning("tree.sync failed: %s", e)
            synced = True
        # Seed provider state silently so first poll doesn't spam.
        if cfg.alert_channel_id:
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
        for loop in (hourly, poll_or, poll_oc):
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
