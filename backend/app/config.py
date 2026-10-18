"""Runtime settings. Everything is read from the environment; nothing secret is hard-coded."""
import hashlib
import hmac
import os


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value is not None and value != "" else default


DAY1_SALT: str = os.environ.get("DAY1_SALT", "")
DAY2_SALT: str = os.environ.get("DAY2_SALT", "")
DATABASE_URL: str = _env("DATABASE_URL", "postgresql://nascon:nascon@db:5432/nascon")
REDIS_URL: str = _env("REDIS_URL", "redis://redis:6379/0")
JWT_TTL_SECONDS: int = int(_env("JWT_TTL_SECONDS", "7200"))
RATE_LIMIT_REQUESTS: int = int(_env("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW_SECONDS: float = float(_env("RATE_LIMIT_WINDOW_SECONDS", "10"))
MAX_BODY_BYTES: int = 1024 * 1024

# Phase II: public URLs handed to clients, and internal service addresses.
PUBLIC_BASE: str = _env("PUBLIC_BASE", "http://localhost:8080")
MEDIA_RTMP_BASE: str = _env("MEDIA_RTMP_BASE", "rtmp://localhost:1935")
MEDIA_HLS_BASE: str = _env("MEDIA_HLS_BASE", "http://localhost:8888")
MEDIA_WEBRTC_BASE: str = _env("MEDIA_WEBRTC_BASE", "http://localhost:8889")
MEDIAMTX_API: str = _env("MEDIAMTX_API", "http://mediamtx:9997")
GUEST_TOKEN_TTL_SECONDS: int = int(_env("GUEST_TOKEN_TTL_SECONDS", "7200"))

# JWT secret: explicit env var, otherwise derived from the team salt so it is never committed.
JWT_SECRET: str = _env("JWT_SECRET") or hmac.new(
    (DAY1_SALT or "unset").encode("utf-8"), b"jwt-signing-key", hashlib.sha256
).hexdigest()
