"""All Ai Hunter tests in one file. Run: python test_all.py"""
import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

import bot as B
import config as C
import providers as P
import xwatch as XW
from xwatch import Tweet, _parse, connect, fetch_user_tweets, is_match, is_seen, mark_seen

# ---------- 1. filter + store ----------
KW = {"require_all": ["free"], "any_of": ["model", "api"]}

ok, hits = is_match("FREE DeepSeek V4.1 Flash API is live", KW)
assert ok and set(hits) == {"free", "api"}, (ok, hits)

ok, _ = is_match("paid model launch next week", KW)
assert not ok, "paid post must not match"

ok, _ = is_match("RT @x free model api", KW)
assert not ok, "retweets must be skipped"
print("section 1 filter/store: PASS")

db = connect(":memory:")
assert not is_seen(db, "123")
mark_seen(db, "123")
assert is_seen(db, "123")
print("ALL FILTER/STORE TESTS PASS")

# ---------- 2. provider free-model detection ----------
assert P.is_free_model({"id": "qwen/qwen3-coder:free", "pricing": {}})
assert P.is_free_model({"id": "x/y", "pricing": {"prompt": "0", "completion": "0"}})
assert not P.is_free_model({"id": "x/y", "pricing": {"prompt": "0.001", "completion": "0"}})
assert not P.is_free_model({"id": "x/y", "pricing": {"prompt": "0", "completion": "0"},
                            "description": "priced at $1 per song"})
assert P.is_opencode_free_model({"id": "big-pickle"})
assert P.is_opencode_free_model({"id": "muse-spark-1.3", "pricing": {"prompt": 0, "completion": 0}})
assert not P.is_opencode_free_model({"id": "gpt-5", "pricing": {"prompt": 1, "completion": 2}})
assert P.is_infron_free_model({"model_id": "qwen/qwen3.8-27b:free", "display_name": "x"})
assert P.is_infron_free_model({"model_id": "motif/motif-3", "display_name": "Motif: Motif 3 (Free)"})
assert not P.is_infron_free_model({"model_id": "qwen/qwen3.8-max", "display_name": "Qwen Max"})
print("ALL PROVIDER TESTS PASS")

# ---------- 3. fix-pass: RT variants, backoff, empty-feed, dry-run ----------
ok, _ = is_match("  RT @x free model api", KW)
assert not ok, "indented RT must be skipped"
ok, _ = is_match("RT: free model api", KW)
assert not ok, "RT: must be skipped"

sleeps = []


async def fake_sleep(d):
    sleeps.append(d)


async def always_none(session, url, handle, timeout):
    return None


XW._try_fetch, orig_try = always_none, XW._try_fetch
XW.asyncio.sleep, orig_sleep = fake_sleep, XW.asyncio.sleep
try:
    async def go():
        import aiohttp
        async with aiohttp.ClientSession() as s:
            return await fetch_user_tweets("h", s, "http://a", ["http://b", "http://c"])
    got = asyncio.run(go())
finally:
    XW._try_fetch, XW.asyncio.sleep = orig_try, orig_sleep
assert got == [], got
# No sleep after the final base fails: there is nothing left to retry,
# so 3 bases produce exactly the 2 inter-attempt delays [1, 2].
assert sleeps == [1, 2], sleeps
print("backoff delays:", sleeps)

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
    db = connect(":memory:")
    n = asyncio.run(B.check_once(None, type("C", (), {"dry_run": True, "rsshub_base": "x", "fallbacks": []})(), KW, db, ["SomeHandle"]))
finally:
    B.fetch_user_tweets = orig_fetch
assert n == 0
assert any("SomeHandle" in m for m in records), records
print("empty-feed log: PASS")


async def one_fetch(handle, session, base, fallbacks=None, timeout=20):
    return [Tweet(handle, "t1", "FREE model API launch", "https://x.com/h/status/t1", datetime.now(timezone.utc))]


B.fetch_user_tweets, orig_fetch2 = one_fetch, B.fetch_user_tweets
try:
    db2 = connect(":memory:")
    n2 = asyncio.run(B.check_once(None, type("C", (), {"dry_run": True, "rsshub_base": "x", "fallbacks": []})(), KW, db2, ["h"]))
finally:
    B.fetch_user_tweets = orig_fetch2
assert n2 == 1, n2
assert not is_seen(db2, "t1"), "dry run must not mark seen"
print("dry-run-no-mark: PASS")
print("ALL FIX-PASS TESTS PASS")

# ---------- 4. regressions ----------
RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>t</title>
<item><title>FREE model photo</title><link>https://x.com/foo/status/1111111111111111111/photo/1</link></item>
<item><title>FREE model query</title><link>https://x.com/foo/status/2222222222222222222?s=20</link></item>
<item><title>FREE model guid</title><link></link><guid isPermaLink="false">3333333333333333333</guid></item>
<item><title>FREE model nolink</title></item>
</channel></rss>"""


def ids_for(handle: str):
    return [t.id for t in _parse(feedparser.parse(RSS), handle)]


ids = ids_for("foo")
assert ids[0] == "1111111111111111111", ids
assert ids[1] == "2222222222222222222", ids
assert ids[2] == "3333333333333333333", ids
assert all(ids), ids
assert len(set(ids)) == len(ids), ids
assert ids == ids_for("foo"), "ids must be stable across fetches"
assert ids_for("bar")[3] != ids[3], "hash fallback must be handle-scoped"
print("tweet-id extraction: PASS")

assert Path(B.BASE_DIR).is_absolute(), B.BASE_DIR
assert (Path(B.BASE_DIR) / "accounts.json").is_file(), B.BASE_DIR
assert (Path(B.BASE_DIR) / "keywords.json").is_file(), B.BASE_DIR
print("BASE_DIR: PASS")

saved = dict(os.environ)
try:
    os.environ["DRY_RUN"] = "1"
    os.environ["CHANNEL_ID"] = "123"
    for name, value in (("POLL_INTERVAL_SECONDS", "soon"), ("ALERT_CHANNEL_ID", "#alerts")):
        os.environ[name] = value
        try:
            C.load()
            raise AssertionError(f"{name}={value!r} must raise ConfigError")
        except C.ConfigError:
            pass
        finally:
            del os.environ[name]
finally:
    os.environ.clear()
    os.environ.update(saved)
print("config int errors: PASS")

saved2 = dict(os.environ)
try:
    os.environ["DRY_RUN"] = "1"
    os.environ["CHANNEL_ID"] = "123"
    os.environ.pop("POLL_INTERVAL_SECONDS", None)
    assert C.load().poll_interval == 1800, C.load().poll_interval
    os.environ["POLL_INTERVAL_SECONDS"] = "10"
    assert C.load().poll_interval == 60, C.load().poll_interval
finally:
    os.environ.clear()
    os.environ.update(saved2)
print("poll interval default/floor: PASS")

models = {f"m{i:03d}": {"id": f"m{i:03d}", "name": f"Model {i:03d}"} for i in range(460)}
pages = P.make_list_embeds(models, "OpenRouter Free Models")
assert len(pages) == 10, len(pages)
assert "260 more models not shown" in (pages[-1].description or ""), (pages[-1].description or "")[-160:]
print("embed truncation notice: PASS")

leftovers = [p.name for p in Path(B.BASE_DIR).iterdir()
             if p.name == "Dockerfile" or p.name == ".dockerignore"
             or p.name.startswith("docker-compose")]
assert not leftovers, leftovers
print("docker files removed: PASS")

c = P.ProviderCache(free={}, fetched_at=time.monotonic(), registry={})
assert c.valid(), "fresh-but-empty cache must be valid"
assert not P.ProviderCache().valid(), "never-fetched cache must be invalid"
print("empty cache validity: PASS")

big_free = {f"live{i:04d}": {"id": f"live{i:04d}", "name": f"Live {i}"} for i in range(100)}
cache = P.ProviderCache()
cache.registry = {f"old{i:05d}": {"id": f"old{i:05d}"} for i in range(5000)}
P._remember(cache, big_free)
assert len(cache.registry) <= P.REGISTRY_CAP, len(cache.registry)
assert all(mid in cache.registry for mid in big_free), "live ids must survive eviction"
print("registry cap: PASS")

nasty = "*hi* _yo_ `x` ~s~ |> " * 400
tw = Tweet(handle="h", id="t1", text=nasty, url="https://x.com/h/status/t1",
           created_utc=datetime.now(timezone.utc))
em = B.build_embed(tw, ["free"])
assert len(em.description or "") <= 4096, len(em.description or "")
print("embed length bound: PASS")

assert XW.is_match("RT@someone great FREE model API", {"require_all": ["free"], "any_of": []})[0] is False
assert XW.is_match("New FREE model API launch", {"require_all": ["free"], "any_of": []}) == (True, ["free"])
print("rt-variant filter: PASS")

_now = datetime.now(timezone.utc)
_old = Tweet(handle="h", id="old1", text="FREE model API launch",
             url="https://x.com/h/status/old1", created_utc=_now - timedelta(hours=25))
_fresh = Tweet(handle="h", id="new1", text="FREE model API launch",
               url="https://x.com/h/status/new1", created_utc=_now)
_KW2 = {"require_all": ["free"], "any_of": []}


async def _two_fetch(handle, session, base, fallbacks=None, timeout=20):
    return [_old, _fresh]


B.fetch_user_tweets, _orig_fetch = _two_fetch, B.fetch_user_tweets
try:
    _dbw = connect(":memory:")
    _Cfg = type("C", (), {"dry_run": True, "rsshub_base": "x", "fallbacks": []})
    _n_win = asyncio.run(B.check_once(None, _Cfg(), _KW2, _dbw, ["h"], max_age_hours=24))
    assert _n_win == 1, _n_win
    _n_all = asyncio.run(B.check_once(None, _Cfg(), _KW2, _dbw, ["h"]))
    assert _n_all == 2, _n_all
finally:
    B.fetch_user_tweets = _orig_fetch
print("xpost 24h window: PASS")

print("ALL TESTS PASS")
