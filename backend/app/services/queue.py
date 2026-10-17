"""Domain events to the internal queue (Redis Streams). Publishing never fails a request."""
import json
import logging

import redis

from .. import config
from ..domain.validate import utc_now_iso

STREAM = "domain-events"
log = logging.getLogger("nascon.queue")
_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(config.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
    return _client


def emit(event_type: str, subject_id: str, data: dict | None = None) -> None:
    event = {"type": event_type, "subject_id": subject_id, "at": utc_now_iso(), "data": data or {}}
    try:
        _redis().xadd(STREAM, {"event": json.dumps(event)}, maxlen=10000, approximate=True)
    except Exception as exc:  # queue outage must not break the request path
        log.warning("queue publish failed: %s", exc)
