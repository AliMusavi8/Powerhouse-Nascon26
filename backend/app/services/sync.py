"""Replay of offline-queued actions with per-action conflict resolution (spec 5.14)."""
import threading

from .. import crypto, db
from ..db import J
from ..domain import sync as rules
from ..domain.scoring import validate_envelope as validate_event
from ..domain.roster import validate_transfer
from ..errors import ApiError
from . import matches, roster

_device_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock(device_id: str) -> threading.Lock:
    with _guard:
        return _device_locks.setdefault(device_id, threading.Lock())


def replay(body: dict) -> dict:
    actions = rules.validate_envelope(body)
    device = body["device_id"]
    results: list[dict | None] = [None] * len(actions)
    with _lock(device):
        for n, idx in enumerate(rules.processing_order(actions), start=1):
            results[idx] = _process(device, actions[idx], n)
    return {"device_id": device, "results": results, "summary": rules.summarize(results)}


def _process(device: str, action: dict, order: int) -> dict:
    aid = action["action_id"]
    with db.tx() as cur:
        cur.execute("SELECT result FROM sync_actions WHERE device_id = %s AND action_id = %s", (device, aid))
        if cur.fetchone():
            version = _current_version(cur, action)
            return rules.result(aid, "duplicate", "skipped_duplicate", None, order, version)
    if action["type"] == "score_event":
        res = _score_event(action, order)
    else:
        res = _roster_transfer(action, order)
    with db.tx() as cur:
        cur.execute("INSERT INTO sync_actions (device_id, action_id, result) VALUES (%s,%s,%s) "
                    "ON CONFLICT DO NOTHING", (device, aid, J(res)))
    return res


def _current_version(cur, action: dict) -> int:
    p = action["payload"]
    if action["type"] == "score_event":
        cur.execute("SELECT COUNT(*) AS n FROM events WHERE match_id = %s", (p.get("match_id"),))
        return cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM roster_audit WHERE league_id = %s AND player_id = %s",
                (p.get("league_id"), p.get("player_id")))
    return cur.fetchone()["n"]


def _score_event(action: dict, order: int) -> dict:
    aid, ev = action["action_id"], action["payload"]
    try:
        validate_event(ev)
    except ApiError as e:
        return rules.result(aid, "rejected", "server_wins", e.code, order, 0)
    with db.tx() as cur:
        version = _current_version(cur, action)
        cur.execute("SELECT body_hash FROM events WHERE event_id = %s", (ev["event_id"],))
        existing = cur.fetchone()
        clean = {"event_id": ev["event_id"], "match_id": ev["match_id"], "type": ev["type"], "payload": ev["payload"]}
        if existing and existing["body_hash"] == crypto.body_hash(clean):
            return rules.result(aid, "duplicate", "skipped_duplicate", None, order, version)
        cur.execute("SELECT 1 FROM matches WHERE match_id = %s", (ev["match_id"],))
        if cur.fetchone() is None and ev["type"] != "match_init":
            return rules.result(aid, "rejected", "server_wins", "MATCH_NOT_FOUND", order, version)
    if action["base_version"] > version:
        return rules.result(aid, "rejected", "server_wins", "INVALID_BASE_VERSION", order, version)
    try:
        _, resp = matches.append_event(ev)
    except ApiError as e:
        return rules.result(aid, "rejected", "server_wins", e.code, order, version)
    resolution = "appended" if action["base_version"] == version else "rebased_append"
    return rules.result(aid, "applied", resolution, None, order, resp["match_version"], resp["signature"])


def _roster_transfer(action: dict, order: int) -> dict:
    aid, tr = action["action_id"], action["payload"]
    try:
        validate_transfer(tr)
    except ApiError as e:
        return rules.result(aid, "rejected", "server_wins", e.code, order, 0)
    with db.tx() as cur:
        version = _current_version(cur, action)
        cur.execute("SELECT 1 FROM roster_requests WHERE request_id = %s", (tr["request_id"],))
        if cur.fetchone():
            return rules.result(aid, "duplicate", "skipped_duplicate", None, order, version)
        cur.execute("SELECT 1 FROM roster_leagues WHERE league_id = %s", (tr["league_id"],))
        if cur.fetchone() is None:
            return rules.result(aid, "rejected", "server_wins", "LEAGUE_NOT_FOUND", order, version)
        cur.execute("SELECT 1 FROM registrations WHERE league_id = %s AND player_id = %s",
                    (tr["league_id"], tr["player_id"]))
        if cur.fetchone() is None:
            return rules.result(aid, "rejected", "server_wins", "PLAYER_NOT_FOUND", order, version)
    if action["base_version"] > version:
        return rules.result(aid, "rejected", "server_wins", "INVALID_BASE_VERSION", order, version)
    try:
        roster.transfer(tr)
    except ApiError as e:
        return rules.result(aid, "rejected", "server_wins", e.code, order, version)
    with db.tx() as cur:
        new_version = _current_version(cur, action)
    resolution = "appended" if action["base_version"] == version else "rebased_append"
    return rules.result(aid, "applied", resolution, None, order, new_version)
