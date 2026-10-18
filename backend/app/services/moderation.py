"""Chat moderation probe, live chat with ordered sequence numbers, and the notification DLQ (spec 5.8, FR-5.2)."""
import time

from .. import crypto, db
from ..db import J
from ..domain import dlq, moderation as rules
from ..domain.validate import utc_now_iso
from ..errors import ApiError, validation
from . import realtime


def _persist_actions(cur, room: str, kicked: list[str], muted: list[str]) -> None:
    rows = [(room, u, "kicked") for u in kicked] + [(room, u, "muted") for u in muted]
    if rows:
        cur.executemany("INSERT INTO moderation_state (chat_room_id, user_id, kind) VALUES (%s,%s,%s) "
                        "ON CONFLICT DO NOTHING", rows)


def enqueue_failures(cur, count: int, room: str) -> None:
    now = utc_now_iso()
    for _ in range(count):
        e = dlq.dead_letter("notification.delivery_failed", "push:" + room, {"chat_room_id": room},
                            dlq.MAX_ATTEMPTS, "simulated downstream failure", now)
        cur.execute("INSERT INTO dlq (event_id, type, target, payload, attempts, last_error, failed_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (e["event_id"], e["type"], e["target"], J(e["payload"]), e["attempts"], e["last_error"],
                     e["failed_at"]))


def dlq_status(cur, limit: int = 100) -> dict:
    cur.execute("SELECT COUNT(*) AS n FROM dlq")
    depth = int(cur.fetchone()["n"])
    events = []
    if depth:
        cur.execute("SELECT event_id, type, target, attempts, last_error, failed_at FROM dlq ORDER BY id LIMIT %s",
                    (limit,))
        events = [dlq.public(r) for r in cur.fetchall()]
    return {"queue_depth": depth, "undelivered_events": events}


def probe(body: dict) -> dict:
    req = rules.validate_request(body)
    room = req["chat_room_id"]
    result = rules.moderate(req["incoming_messages"])
    with db.tx() as cur:
        _persist_actions(cur, room, result["kicked_users"], result["muted_users"])
        if req["simulate_failed_notifications"] > 0:
            enqueue_failures(cur, req["simulate_failed_notifications"], room)
        status = dlq_status(cur)
    signature = crypto.sign_day2(room, rules.sig_payload(room, result["flagged_count"], result["kicked_users"],
                                                         status["queue_depth"]))
    return {"chat_room_id": room, "filtered_messages": result["filtered_messages"],
            "kicked_users": result["kicked_users"], "muted_users": result["muted_users"], "dlq_status": status,
            "signature": signature}


def dlq_depth() -> int:
    with db.tx() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM dlq")
        return int(cur.fetchone()["n"])


# ---------------------------------------------------------------- live chat (members only)

_windows: dict[tuple[str, str], list[float]] = {}


def _rate_limited(room: str, sender: str, now: float) -> bool:
    q = [t for t in _windows.get((room, sender), []) if now - t < 2.0]
    q.append(now)
    _windows[(room, sender)] = q
    return len(q) > rules.RATE_LIMIT_MESSAGES


def post(room: str, sender: str, text) -> dict:
    if not isinstance(room, str) or not room or not isinstance(text, str) or not (1 <= len(text) <= 500):
        raise validation(["chat_room_id", "text"])
    with db.tx() as cur:
        cur.execute("SELECT kind FROM moderation_state WHERE chat_room_id = %s AND user_id = %s", (room, sender))
        if cur.fetchone():
            raise ApiError(403, "FORBIDDEN", "You have been removed from this chat.")
    reason, clean = rules.classify(text)
    if reason is None and _rate_limited(room, sender, time.monotonic()):
        reason = "rate_limit_exceeded"
    with db.tx() as cur:
        if reason in ("flood_character_repeat", "rate_limit_exceeded"):
            _persist_actions(cur, room, [], [sender])
            raise ApiError(429, "RATE_LIMITED", "Message blocked by the chat flood filter.", {"reason": reason})
        cur.execute("INSERT INTO chat_rooms (chat_room_id) VALUES (%s) ON CONFLICT DO NOTHING", (room,))
        cur.execute("UPDATE chat_rooms SET seq = seq + 1 WHERE chat_room_id = %s RETURNING seq", (room,))
        seq = cur.fetchone()["seq"]
        message_id = f"{room}-{seq}"
        cur.execute("INSERT INTO chat_messages (chat_room_id, seq, message_id, sender, text, flagged, reason) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)", (room, seq, message_id, sender, clean, reason is not None, reason))
        if reason == "profanity_leetspeak":
            _persist_actions(cur, room, [sender], [])
    msg = {"type": "chat", "chat_room_id": room, "seq": seq, "message_id": message_id, "sender": sender,
           "text": clean, "flagged": reason is not None, "reason": reason}
    realtime.publish("chat:" + room, msg)
    return msg


def history(room: str, limit: int = 50) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT seq, message_id, sender, text, flagged, reason FROM chat_messages WHERE chat_room_id = %s "
                    "ORDER BY seq DESC LIMIT %s", (room, limit))
        rows = list(reversed(cur.fetchall()))
    return {"chat_room_id": room, "messages": [dict(r, type="chat", chat_room_id=room) for r in rows]}
