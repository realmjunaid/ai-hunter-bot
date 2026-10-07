"""TDD tests for filter + store. Run: python test_filter.py"""
from filter import is_match
from store import connect, is_seen, mark_seen

KW = {"require_all": ["free"], "any_of": ["model", "api"]}

ok, hits = is_match("FREE DeepSeek V4.1 Flash API is live", KW)
assert ok and set(hits) == {"free", "api"}, (ok, hits)

ok, _ = is_match("paid model launch next week", KW)
assert not ok, "paid post must not match"

ok, _ = is_match("RT @x free model api", KW)
assert not ok, "retweets must be skipped"

db = connect(":memory:")
assert not is_seen(db, "123")
mark_seen(db, "123")
assert is_seen(db, "123")
print("ALL FILTER/STORE TESTS PASS")
