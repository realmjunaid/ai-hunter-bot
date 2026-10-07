"""Keyword filter for free-AI-model posts."""


def is_match(text: str, keywords: dict) -> tuple:
    low = text.lower().strip()
    if low.startswith("rt @") or low.startswith("rt:") or low.startswith("@"):
        return False, []
    hits = [w for w in keywords.get("require_all", []) if w.lower() in low]
    if len(hits) < len(keywords.get("require_all", [])):
        return False, []
    any_hits = [w for w in keywords.get("any_of", []) if w.lower() in low]
    if keywords.get("any_of") and not any_hits:
        return False, []
    return True, hits + any_hits
