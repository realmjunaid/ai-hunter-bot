"""Regression tests for the bug-fix pass. Run: python test_regressions.py"""
import os
from pathlib import Path

import feedparser

import bot as B
import config as C
import providers as P
from fetcher import _parse

# 1. Tweet ids: photo/query URLs must resolve to the status id, never collide,
#    never be empty (an empty id would mark every later tweet as already seen).
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

# 2. BASE_DIR must point at the app folder regardless of caller cwd / OS.
assert Path(B.BASE_DIR).is_absolute(), B.BASE_DIR
assert (Path(B.BASE_DIR) / "accounts.json").is_file(), B.BASE_DIR
assert (Path(B.BASE_DIR) / "keywords.json").is_file(), B.BASE_DIR
print("BASE_DIR: PASS")

# 3. Bad integer env vars must raise ConfigError, not a raw ValueError.
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

# 3b. Provider poll default must be 30 minutes (1800s), floor 60s.
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

# 4. More than 10 embed pages must not silently drop models.
models = {f"m{i:03d}": {"id": f"m{i:03d}", "name": f"Model {i:03d}"} for i in range(460)}
pages = P.make_list_embeds(models, "OpenRouter Free Models")
assert len(pages) == 10, len(pages)
assert "260 more models not shown" in (pages[-1].description or ""), (pages[-1].description or "")[-160:]
print("embed truncation notice: PASS")

# 5. Docker support was intentionally removed: no Dockerfile/.dockerignore
#    must remain in the repo.
leftovers = [p.name for p in Path(B.BASE_DIR).iterdir()
             if p.name == "Dockerfile" or p.name == ".dockerignore"
             or p.name.startswith("docker-compose")]
assert not leftovers, leftovers
print("docker files removed: PASS")

# 6. Empty free-model results must still count as a valid cache entry,
#    otherwise every command refetches (cache stampede on zero-free days).
import time as _time

c = P.ProviderCache(free={}, fetched_at=_time.monotonic(), registry={})
assert c.valid(), "fresh-but-empty cache must be valid"
assert not P.ProviderCache().valid(), "never-fetched cache must be invalid"
print("empty cache validity: PASS")

# 7. The removed-model registry must be capped and must always keep live ids.
big_free = {f"live{i:04d}": {"id": f"live{i:04d}", "name": f"Live {i}"} for i in range(100)}
cache = P.ProviderCache()
cache.registry = {f"old{i:05d}": {"id": f"old{i:05d}"} for i in range(5000)}
P._remember(cache, big_free)
assert len(cache.registry) <= P.REGISTRY_CAP, len(cache.registry)
assert all(mid in cache.registry for mid in big_free), "live ids must survive eviction"
print("registry cap: PASS")

# 8. Escape-heavy tweet text must never push the embed past Discord's limit.
from datetime import datetime, timezone

from fetcher import Tweet

nasty = "*hi* _yo_ `x` ~s~ |> " * 400
tw = Tweet(handle="h", id="t1", text=nasty, url="https://x.com/h/status/t1",
           created_utc=datetime.now(timezone.utc))
em = B.build_embed(tw, ["free"])
assert len(em.description or "") <= 4096, len(em.description or "")
print("embed length bound: PASS")

# 9. "RT@" without a space is still a retweet, not original content.
import filter as F

assert F.is_match("RT@someone great FREE model API", {"require_all": ["free"], "any_of": []})[0] is False
assert F.is_match("New FREE model API launch", {"require_all": ["free"], "any_of": []}) == (True, ["free"])
print("rt-variant filter: PASS")

# 10. /xpost 24h window: stale tweets skipped, fresh ones posted;
#     the unfiltered (hourly) path still posts everything unseen.
import asyncio as _asyncio
import store as _store
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
from fetcher import Tweet as _Tweet

_now = _dt.now(_tz.utc)
_old = _Tweet(handle="h", id="old1", text="FREE model API launch",
              url="https://x.com/h/status/old1", created_utc=_now - _td(hours=25))
_fresh = _Tweet(handle="h", id="new1", text="FREE model API launch",
                url="https://x.com/h/status/new1", created_utc=_now)
_KW2 = {"require_all": ["free"], "any_of": []}


async def _two_fetch(handle, session, base, fallbacks=None, timeout=20):
    return [_old, _fresh]


B.fetch_user_tweets, _orig_fetch = _two_fetch, B.fetch_user_tweets
try:
    _dbw = _store.connect(":memory:")
    _Cfg = type("C", (), {"dry_run": True, "rsshub_base": "x", "fallbacks": []})
    _n_win = _asyncio.run(B.check_once(None, _Cfg(), _KW2, _dbw, ["h"], max_age_hours=24))
    assert _n_win == 1, _n_win
    _n_all = _asyncio.run(B.check_once(None, _Cfg(), _KW2, _dbw, ["h"]))
    assert _n_all == 2, _n_all
finally:
    B.fetch_user_tweets = _orig_fetch
print("xpost 24h window: PASS")

print("ALL REGRESSION TESTS PASS")
