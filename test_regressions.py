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

# 4. More than 10 embed pages must not silently drop models.
models = {f"m{i:03d}": {"id": f"m{i:03d}", "name": f"Model {i:03d}"} for i in range(460)}
pages = P.make_list_embeds(models, "OpenRouter Free Models")
assert len(pages) == 10, len(pages)
assert "260 more models not shown" in (pages[-1].description or ""), (pages[-1].description or "")[-160:]
print("embed truncation notice: PASS")

# 5. Dockerfile must ship every module (it omitted providers.py -> image crash).
copy_lines = [ln.strip() for ln in (Path(B.BASE_DIR) / "Dockerfile").read_text(encoding="utf-8").splitlines()
              if ln.strip().upper().startswith("COPY")]
assert copy_lines, "no COPY lines in Dockerfile"
assert any("*.py" in ln or "providers.py" in ln or ln.rstrip().endswith(".") for ln in copy_lines), copy_lines
print("dockerfile copies providers: PASS")

print("ALL REGRESSION TESTS PASS")
