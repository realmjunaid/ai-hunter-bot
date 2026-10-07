"""Tests for providers free-model detection. Run: python test_providers.py"""
from providers import is_free_model, is_opencode_free_model

assert is_free_model({"id": "qwen/qwen3-coder:free", "pricing": {}})
assert is_free_model({"id": "x/y", "pricing": {"prompt": "0", "completion": "0"}})
assert not is_free_model({"id": "x/y", "pricing": {"prompt": "0.001", "completion": "0"}})
assert not is_free_model({"id": "x/y", "pricing": {"prompt": "0", "completion": "0"},
                           "description": "priced at $1 per song"})
assert is_opencode_free_model({"id": "big-pickle"})
assert is_opencode_free_model({"id": "muse-spark-1.3", "pricing": {"prompt": 0, "completion": 0}})
assert not is_opencode_free_model({"id": "gpt-5", "pricing": {"prompt": 1, "completion": 2}})
print("ALL PROVIDER TESTS PASS")
