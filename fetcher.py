"""Fetch recent tweets per handle via RSSHub (RSS). No login, no paid API."""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp
import feedparser

log = logging.getLogger("aihunter")

ROUTE = "/twitter/user/{handle}"


@dataclass
class Tweet:
    handle: str
    id: str
    text: str
    url: str
    created_utc: datetime


def _parse(feed, handle: str) -> list:
    out = []
    for e in feed.entries:
        link = getattr(e, "link", "")
        tid = link.rstrip("/").split("/")[-1].split("?")[0] or getattr(e, "id", "")
        text = getattr(e, "title", "") or ""
        if hasattr(e, "published_parsed") and e.published_parsed:
            created = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        else:
            created = datetime.now(timezone.utc)
        out.append(Tweet(handle=handle, id=str(tid), text=text, url=link, created_utc=created))
    return out


async def _try_fetch(session, url: str, handle: str, timeout: int):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            if r.status != 200:
                return None
            body = await r.read()
    except Exception:
        return None
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        return None
    return _parse(feed, handle)


async def fetch_user_tweets(handle: str, session, base: str, fallbacks=None, timeout: int = 20) -> list:
    """Try base then each fallback with exponential backoff. All fail -> []."""
    bases = [base] + list(fallbacks or [])
    for i, b in enumerate(bases):
        got = await _try_fetch(session, b.rstrip("/") + ROUTE.format(handle=handle), handle, timeout)
        if got is not None:
            if i:
                log.info("fetch %s ok via fallback %s", handle, b)
            return got
        log.warning("fetch %s failed via %s", handle, b)
        await asyncio.sleep(2 ** i)
    return []
