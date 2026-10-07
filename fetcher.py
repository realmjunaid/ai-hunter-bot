"""Fetch recent tweets per handle via RSSHub (RSS). No login, no paid API."""
import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp
import feedparser

log = logging.getLogger("aihunter")

ROUTE = "/twitter/user/{handle}"
# X status ids live anywhere in the URL path: /status/123, /status/123/photo/1, ...
STATUS_ID_RE = re.compile(r"/status(?:es)?/(\d+)", re.IGNORECASE)


@dataclass
class Tweet:
    handle: str
    id: str
    text: str
    url: str
    created_utc: datetime


def _entry_id(entry, link: str, handle: str) -> str:
    """Stable, non-empty tweet id for dedupe.

    Taking the last URL segment blindly turns ``/status/123/photo/1`` into ``1``,
    so unrelated photo posts collide in seen.db and get silently dropped.
    """
    guid = str(getattr(entry, "id", "") or "").strip()
    for candidate in (link, guid):
        m = STATUS_ID_RE.search(candidate or "")
        if m:
            return m.group(1)
    # feedparser falls back to the link when a feed has no guid, so only keep
    # a guid that is genuinely distinct from the link.
    if guid and guid != (link or "").strip():
        return guid
    # Last resort: never emit "" (every empty id would dedupe to one row).
    text = str(getattr(entry, "title", "") or "")
    return "x-" + hashlib.sha1(f"{handle}\n{link}\n{text}".encode("utf-8")).hexdigest()[:24]


def _parse(feed, handle: str) -> list:
    out = []
    for e in feed.entries:
        link = getattr(e, "link", "") or ""
        tid = _entry_id(e, link, handle)
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
