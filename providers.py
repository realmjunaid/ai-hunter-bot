"""Provider watch: OpenRouter + OpenCode Zen free-model tracking.

Pure fetch/detect/history/embed logic. Discord wiring (loops, commands)
lives in bot.py and calls register_commands() + poll_providers().
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime as dt, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import discord

BASE_DIR = Path(__file__).resolve().parent
try:
    DHK = ZoneInfo("Asia/Dhaka")
except ZoneInfoNotFoundError:
    from datetime import timedelta
    DHK = timezone(timedelta(hours=6))  # Windows without tzdata

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENCODE_MODELS_URL = "https://opencode.ai/zen/v1/models"

PROVIDER_LINKS = {
    "OpenRouter": "https://openrouter.ai/models?variant=free",
    "OpenCode Zen": "https://opencode.ai/docs/zen/#models",
}

C_OREO = 0x57F287
C_SUCCESS = 0x57F287
C_DANGER = 0xED4245
C_INFO = 0x57F287

CACHE_TTL = 90.0
HISTORY_RETENTION_DAYS = 30
MAX_ALERT_MODELS = 12

log = logging.getLogger("aihunter.providers")


class HistoryStore:
    """Atomic JSON history {model_id: first_seen_iso} with legacy compat + pruning."""

    def __init__(self, primary: Path, legacy: Path) -> None:
        self.primary = primary
        self.legacy = legacy
        self.data: Dict[str, str] = self._load()

    def _load(self) -> Dict[str, str]:
        for path in (self.primary, self.legacy):
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        if isinstance(raw.get("history"), dict):
                            return {str(k): str(v) for k, v in raw["history"].items()}
                        if isinstance(raw.get("ids"), list):
                            now = dt.now(timezone.utc).isoformat()
                            return {str(mid): now for mid in raw["ids"]}
                except Exception as e:
                    log.warning("history load failed %s: %s", path.name, e)
        return {}

    def save(self) -> None:
        try:
            self.prune(HISTORY_RETENTION_DAYS)
            payload = {"history": self.data, "updated_at": dt.now(timezone.utc).isoformat()}
            tmp = self.primary.with_suffix(self.primary.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.primary)
            compat = {"ids": sorted(self.data.keys()), "updated_at": payload["updated_at"]}
            self.legacy.write_text(json.dumps(compat, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.error("history save failed %s: %s", self.primary.name, e)

    def touch(self, ids: set) -> bool:
        now = dt.now(timezone.utc).isoformat()
        changed = False
        for mid in ids:
            if mid not in self.data:
                self.data[mid] = now
                changed = True
        return changed

    def remove(self, ids: set) -> None:
        for mid in ids:
            self.data.pop(mid, None)

    def prune(self, keep_days: int) -> None:
        cutoff = dt.now(timezone.utc) - datetime.timedelta(days=keep_days)
        stale = [mid for mid, iso in self.data.items()
                 if (ts := parse_iso(iso)) is not None and ts < cutoff]
        for mid in stale:
            del self.data[mid]

    @property
    def ids(self) -> set:
        return set(self.data.keys())


def parse_iso(value: str) -> Optional[dt]:
    try:
        parsed = dt.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


_session: Optional[aiohttp.ClientSession] = None


def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300, enable_cleanup_closed=True)
        timeout = aiohttp.ClientTimeout(total=20, connect=8)
        _session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _session


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


def openrouter_headers() -> Dict[str, str]:
    headers = {
        "HTTP-Referer": "https://discord.com",
        "X-Title": "Ai Hunter",
        "User-Agent": "AiHunter/1.0 (Discord Bot; Free Model Tracker)",
    }
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def opencode_headers() -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AiHunter/1.0",
        "Accept": "application/json",
    }


async def fetch_json(url: str, headers: Dict[str, str]) -> List[dict]:
    session = get_session()
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            body = (await resp.text())[:300]
            raise RuntimeError(f"API {resp.status}: {body}")
        data = await resp.json()
        models = data.get("data", [])
        return models if isinstance(models, list) else []


def _to_float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def is_free_model(m: dict) -> bool:
    mid = str(m.get("id", "")).strip().lower()
    name = str(m.get("name", "")).strip().lower()
    desc = str(m.get("description", "")).strip().lower()
    if mid.endswith(":free") or mid.endswith("-free") or mid.endswith("/free") or mid == "openrouter/free":
        return True
    if "(free)" in name or "[free]" in name:
        return True
    pricing = m.get("pricing")
    if isinstance(pricing, dict) and pricing:
        prompt = _to_float_or_none(pricing.get("prompt"))
        completion = _to_float_or_none(pricing.get("completion"))
        request = _to_float_or_none(pricing.get("request"))
        if prompt == 0.0 and completion == 0.0 and request in (0.0, None):
            if "per song" in desc or "per clip" in desc or "priced at $" in desc:
                return False
            return True
    return False


def is_opencode_free_model(m: dict) -> bool:
    mid = str(m.get("id", "")).strip().lower()
    name = str(m.get("name", "")).strip().lower()
    if mid in ("big-pickle", "free"):
        return True
    if mid.endswith(":free") or mid.endswith("-free") or "/free" in mid or "-free-" in mid:
        return True
    if "(free)" in name or "[free]" in name:
        return True
    pricing = m.get("pricing")
    if isinstance(pricing, dict) and pricing:
        prompt = _to_float_or_none(pricing.get("prompt"))
        completion = _to_float_or_none(pricing.get("completion"))
        if prompt == 0.0 and completion == 0.0:
            return True
    return False


@dataclass
class ProviderCache:
    free: Dict[str, dict] = field(default_factory=dict)
    fetched_at: float = 0.0
    registry: Dict[str, dict] = field(default_factory=dict)

    def valid(self) -> bool:
        return bool(self.free) and (time.monotonic() - self.fetched_at) < CACHE_TTL


or_cache = ProviderCache()
oc_cache = ProviderCache()
or_history = HistoryStore(BASE_DIR / "model_history.json", BASE_DIR / "known_models.json")
oc_history = HistoryStore(BASE_DIR / "opencode_history.json", BASE_DIR / "opencode_known.json")


async def fetch_or_free(force: bool = False) -> Dict[str, dict]:
    if not force and or_cache.valid():
        return or_cache.free
    models = await fetch_json(OPENROUTER_MODELS_URL, openrouter_headers())
    free = {m["id"]: m for m in models if isinstance(m, dict) and m.get("id") and is_free_model(m)}
    or_cache.free = free
    or_cache.fetched_at = time.monotonic()
    or_cache.registry.update(free)
    return free


async def fetch_oc_free(force: bool = False) -> Dict[str, dict]:
    if not force and oc_cache.valid():
        return oc_cache.free
    models = await fetch_json(OPENCODE_MODELS_URL, opencode_headers())
    free = {m["id"]: m for m in models if isinstance(m, dict) and m.get("id") and is_opencode_free_model(m)}
    oc_cache.free = free
    oc_cache.fetched_at = time.monotonic()
    oc_cache.registry.update(free)
    return free


def base_embed(title: str, color: int, url: Optional[str] = None) -> discord.Embed:
    e = discord.Embed(title=title, url=url, color=color, timestamp=dt.now(timezone.utc))
    e.set_footer(text="Ai Hunter")
    return e


def clean_name(m: dict) -> str:
    raw = str(m.get("name", m.get("id", "?")))
    return raw.replace(" (free)", "").replace(" [free]", "").strip() or str(m.get("id", "?"))


def chunk_lines_into_embeds(title: str, total: int, lines: List[str], color: int, url: Optional[str] = None) -> List[discord.Embed]:
    if not lines:
        e = base_embed(f"{title} (0)", C_INFO, url)
        e.description = "No free models available right now."
        return [e]
    embeds: List[discord.Embed] = []
    current: List[str] = []
    current_len = 0
    page = 1
    for line in lines:
        size = len(line) + 2
        if current and (current_len + size > 3500 or len(current) >= 20):
            e = base_embed(f"{title} ({total}) - Page {page}", color, url)
            e.description = "\n\n".join(current)
            embeds.append(e)
            current, current_len, page = [], 0, page + 1
        current.append(line)
        current_len += size
    if current:
        suffix = f" - Page {page}" if embeds else ""
        e = base_embed(f"{title} ({total}){suffix}", color, url)
        e.description = "\n\n".join(current)
        embeds.append(e)
    if len(embeds) == 1:
        embeds[0].title = f"{title} ({total})"
    return embeds[:10]


def make_list_embeds(free: Dict[str, dict], provider_title: str) -> List[discord.Embed]:
    provider = "OpenRouter" if "OpenRouter" in provider_title else "OpenCode Zen"
    url = PROVIDER_LINKS.get(provider)
    ordered = list(free.values())
    lines = [f"{i:02d}. {clean_name(m)}" for i, m in enumerate(ordered, 1)]
    return chunk_lines_into_embeds(provider_title, len(ordered), lines, C_OREO, url)


def make_batch_alert_embed(models: List[dict], is_added: bool, provider: str) -> discord.Embed:
    count = len(models)
    plural = "s" if count != 1 else ""
    title = f"{count} New Free Model{plural} Added" if is_added else f"{count} Free Model{plural} Removed"
    e = base_embed(title, C_SUCCESS if is_added else C_DANGER)
    url = PROVIDER_LINKS.get(provider, "")
    provider_label = f"[{provider}]({url})" if url else provider
    lines = [f"{i:02d}. {clean_name(m)}" for i, m in enumerate(models[:MAX_ALERT_MODELS], 1)]
    e.description = f"Provider: {provider_label}\n\n" + "\n\n".join(lines)
    if count > MAX_ALERT_MODELS:
        e.description += f"\n\n*...and {count - MAX_ALERT_MODELS} more model{plural}*"
    return e


async def send_safe(channel, *args: Any, **kwargs: Any) -> bool:
    try:
        await channel.send(*args, **kwargs)
        return True
    except discord.HTTPException as e:
        log.error("send failed (HTTP %s): %s", getattr(e, "status", "?"), e)
    except Exception as e:
        log.error("send failed: %s", e)
    return False


async def poll_provider(bot, channel_id: int, provider: str, fetch_fn, store: HistoryStore,
                        cache: ProviderCache, lock) -> None:
    """Shared poll: diff ids, alert on add/remove, persist state."""
    if channel_id == 0:
        return
    if lock.locked():
        log.warning("%s poll skipped: previous run still active", provider)
        return
    async with lock:
        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as e:
                log.error("fetch_channel(%s) failed: %s", channel_id, e)
                return
        try:
            free = await fetch_fn(force=True)
        except Exception as e:
            log.error("%s poll fetch failed: %s", provider, e)
            return
        current = set(free.keys())
        known = store.ids
        if not known:
            store.touch(current)
            store.save()
            log.info("initial %s free models registered: %d", provider, len(free))
            return
        added, removed = current - known, known - current
        if not added and not removed:
            if store.touch(current):
                store.save()
            return
        now = dt.now(timezone.utc).isoformat()
        for mid in added:
            store.data.setdefault(mid, now)
        store.remove(removed)
        store.save()
        if added:
            models = [free[mid] for mid in free.keys() if mid in added]
            await send_safe(channel, embed=make_batch_alert_embed(models, True, provider))
        if removed:
            models = [cache.registry.get(mid, {"id": mid, "name": mid}) for mid in removed]
            await send_safe(channel, embed=make_batch_alert_embed(models, False, provider))
        log.info("%s poll diff: +%d added, -%d removed", provider, len(added), len(removed))


def register_commands(tree) -> None:
    @tree.command(name="orfm", description="Show all current OpenRouter free models")
    async def orfm(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            free = await fetch_or_free()
        except Exception as err:
            e = base_embed("Fetch Failed", C_DANGER)
            e.description = f"Could not fetch [OpenRouter]({PROVIDER_LINKS['OpenRouter']}) models:\n```{err}```"
            await interaction.followup.send(embed=e, ephemeral=True)
            return
        await interaction.followup.send(embeds=make_list_embeds(free, "OpenRouter Free Models"))

    @tree.command(name="ocfm", description="Show all current OpenCode Zen free models")
    async def ocfm(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            free = await fetch_oc_free()
        except Exception as err:
            e = base_embed("Fetch Failed", C_DANGER)
            e.description = f"Could not fetch [OpenCode Zen]({PROVIDER_LINKS['OpenCode Zen']}) models:\n```{err}```"
            await interaction.followup.send(embed=e, ephemeral=True)
            return
        await interaction.followup.send(embeds=make_list_embeds(free, "OpenCode Zen Free Models"))

    @tree.command(name="ping", description="Check bot latency")
    async def ping(interaction: discord.Interaction) -> None:
        e = base_embed("Pong!", C_OREO)
        e.description = "Ai Hunter is watching."
        await interaction.response.send_message(embed=e, ephemeral=True)
