"""
core/config.py
--------------
Application configuration, read once from the environment (12-factor).

Includes a tiny dependency-free `.env` loader so local development uses the
same env-var contract as production (see `.env.example`). Real environment
variables always win over `.env` values; nothing here is a secret by default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Populate os.environ defaults from a KEY=VALUE file, ignoring blanks."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, default)
    return value if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    """Immutable snapshot of the effective configuration."""

    # web server
    port: int
    public_base_url: str
    force_https: bool

    # cache backend: SimpleCache (in-process) | RedisCache (+ redis_url)
    cache_type: str
    cache_ttl: int
    redis_url: str

    # rate limiting (flask-limiter syntax, e.g. "300 per minute")
    rate_limit_default: str
    rate_limit_write: str
    rate_limit_storage: str

    # logging
    log_level: str
    json_lines: bool

    # scheduled ingestion cron (UTC)
    ingest_cron_dow: str
    ingest_cron_hour: int
    # cadence for scheduler.py: seconds between runs (0 = weekly cron instead)
    ingest_interval_seconds: int

    # future: Postgres backend (schema is Postgres-compatible)
    database_url: str

    @classmethod
    def from_env(cls) -> "Config":
        _load_env_file(BASE_DIR / ".env")
        return cls(
            port=_env_int("PORT", 5010),
            public_base_url=_env("PUBLIC_BASE_URL", ""),
            force_https=_env_bool("FORCE_HTTPS", False),
            cache_type=_env("CACHE_TYPE", "SimpleCache"),
            cache_ttl=_env_int("CACHE_TTL", 300),
            redis_url=_env("REDIS_URL", "redis://localhost:6379/0"),
            rate_limit_default=_env("RATE_LIMIT_DEFAULT", "300 per minute"),
            rate_limit_write=_env("RATE_LIMIT_WRITE", "60 per minute"),
            rate_limit_storage=_env("RATE_LIMIT_STORAGE", "memory://"),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            json_lines=_env_bool("JSON_LINES", True),
            ingest_cron_dow=_env("INGEST_CRON_DOW", "sat"),
            ingest_cron_hour=_env_int("INGEST_CRON_HOUR", 6),
            ingest_interval_seconds=_env_int("INGEST_INTERVAL_SECONDS", 0),
            database_url=_env("DATABASE_URL", ""),
        )


settings = Config.from_env()