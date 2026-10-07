"""Tests for reviewer fix-pass. Run: python test_botfix.py"""
import asyncio
import logging
import sqlite3
import store
from filter import is_match
from fetcher import Tweet, fetch_user_tweets
from datetime import datetime, timezone

KW = {"require_all": ["free"], "any_of": ["model", "api"]}

# 1. whitespace-prefixed RT / reply variants must be skipped
ok, _ = is_match("  RT @x free model api", KW)
assert not ok, "indented RT must be skipped"
ok, _ = is_match("RT: free model api", KW)
assert not ok, "RT: must be skipped"

# 2. backoff: delays must grow across failing instances
import fetcher as F

sleeps = []


async def fake_sleep(d):
    sleeps.append(d)


async def always_none(session, url, handle, timeout):
    return None


F._try_fetch, orig_try = always_none, F._try_fetch
F.asyncio.sleep, orig_sleep = fake_sleep, F.asyncio.sleep
try:
    async def go():
        import aiohttp
        async with aiohttp.ClientSession() as s:
            return await fetch_user_tweets("h", s, "http://a", ["http://b", "http://c"])
    got = asyncio.run(go())
finally:
    F._try_fetch, F.asyncio.sleep = orig_try, orig_sleep
assert got == [], got
assert len(sleeps) == 3 and sleeps[0] < sleeps[1] < sleeps[2], sleeps
print("backoff delays:", sleeps)

# 3. empty feed must log something (caplog-style via handler)
import bot as B

records = []


class H(logging.Handler):
    def emit(self, r):
        records.append(r.getMessage())


logging.getLogger("aihunter").addHandler(H())
logging.getLogger("aihunter").setLevel(logging.INFO)


async def empty_fetch(handle, session, base, fallbacks=None, timeout=20):
    return []


B.fetch_user_tweets, orig_fetch = empty_fetch, B.fetch_user_tweets
try:
    db = store.connect(":memory:")
    n = asyncio.run(B.check_once(None, type("C", (), {"dry_run": True, "rsshub_base": "x", "fallbacks": []})(), KW, db, ["SomeHandle"]))
finally:
    B.fetch_user_tweets = orig_fetch
assert n == 0
assert any("SomeHandle" in m for m in records), records
print("empty-feed log: PASS")

# 4. dry run must NOT mark seen
async def one_fetch(handle, session, base, fallbacks=None, timeout=20):
    return [Tweet(handle, "t1", "FREE model API launch", "https://x.com/h/status/t1", datetime.now(timezone.utc))]


B.fetch_user_tweets, orig_fetch2 = one_fetch, B.fetch_user_tweets
try:
    db2 = store.connect(":memory:")
    n2 = asyncio.run(B.check_once(None, type("C", (), {"dry_run": True, "rsshub_base": "x", "fallbacks": []})(), KW, db2, ["h"]))
finally:
    B.fetch_user_tweets = orig_fetch2
assert n2 == 1, n2
assert not store.is_seen(db2, "t1"), "dry run must not mark seen"
print("dry-run-no-mark: PASS")
print("ALL FIX-PASS TESTS PASS")
