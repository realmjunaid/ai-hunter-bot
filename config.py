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
    )
