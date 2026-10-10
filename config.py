"""Config loading for Ai Hunter. Secrets come only from env / .env file."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE = "https://rsshub.app"


class ConfigError(Exception):
    pass


@dataclass
class Config:
    token: str
    channel_id: int
    rsshub_base: str = DEFAULT_BASE
    fallbacks: list = field(default_factory=list)
    dry_run: bool = False
    alert_channel_id: int = 0
    poll_interval: int = 300


def _env_int(name: str, default: int) -> int:
    """Parse an optional integer env var, failing with ConfigError (not ValueError)."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None


def load() -> Config:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token and os.getenv("DRY_RUN", "0") != "1":
        raise ConfigError("DISCORD_TOKEN missing in env/.env")
    raw_channel = os.getenv("CHANNEL_ID", "").strip()
    if not raw_channel:
        raise ConfigError("CHANNEL_ID missing in env/.env")
    try:
        channel_id = int(raw_channel)
    except ValueError:
        raise ConfigError("CHANNEL_ID must be an integer")
    base = os.getenv("RSSHUB_BASE", "").strip() or DEFAULT_BASE
    fallbacks = [u.strip().rstrip("/") for u in os.getenv("RSSHUB_FALLBACKS", "").split(",") if u.strip()]
    return Config(
        token=token,
        channel_id=channel_id,
        rsshub_base=base.rstrip("/"),
        fallbacks=fallbacks,
        dry_run=os.getenv("DRY_RUN", "0") == "1",
        alert_channel_id=_env_int("ALERT_CHANNEL_ID", 0),
        # Provider polls (OpenRouter / OpenCode Zen / Infron) run every
        # 30 minutes by default; X watch stays on its own hourly loop.
        poll_interval=max(60, _env_int("POLL_INTERVAL_SECONDS", 1800)),
    )
