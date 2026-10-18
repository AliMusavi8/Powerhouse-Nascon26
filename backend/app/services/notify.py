"""Notification bus (FR-5.2): realtime fan-out plus downstream push delivery with bounded exponential retry.

Every notification is published to its realtime topic. Delivery to the downstream push target is retried up to 3
times (0.1 s, 0.2 s backoff); if it still fails (or the caller sets simulate_dlq) the event is written to the
persistent DLQ that /audit/v1/moderation/test reports.
"""
import json
import logging
import threading
import time

from .. import db
from ..db import J
from ..domain import dlq
from ..domain.validate import utc_now_iso
from . import queue, realtime

log = logging.getLogger("nascon.notify")


def _push(event: dict) -> None:
    """Downstream push gateway: the internal queue the worker fans out to devices."""
    queue.emit("notification." + event["type"], event["target"], event["payload"])


def _dead_letter(event: dict, attempts: int, error: str) -> None:
    e = dlq.dead_letter(event["type"], event["target"], event["payload"], attempts, error, utc_now_iso())
    with db.tx() as cur:
        cur.execute("INSERT INTO dlq (event_id, type, target, payload, attempts, last_error, failed_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (e["event_id"], e["type"], e["target"], J(e["payload"]), e["attempts"], e["last_error"],
                     e["failed_at"]))
    from . import moderation
    moderation.invalidate()


def _deliver(event: dict) -> None:
    ok, attempts, error = dlq.deliver(_push, event, sleep=time.sleep)
    if not ok:
        log.warning("notification %s to %s dead-lettered after %s attempts: %s", event["type"], event["target"],
                    attempts, error)
        _dead_letter(event, attempts, error or "delivery failed")


def dispatch(event_type: str, target: str, payload: dict, simulate_dlq: bool = False, wait: bool = False) -> None:
    event = {"type": event_type, "target": target, "payload": json.loads(json.dumps(payload, default=str)),
             "simulate_dlq": bool(simulate_dlq)}
    realtime.publish("notify:" + target, dict(event["payload"], type=event_type))
    if wait:
        _deliver(event)
    else:
        threading.Thread(target=_deliver, args=(event,), daemon=True).start()
