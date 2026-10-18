"""Prometheus metrics (NFR-6) and right-to-erasure (NFR-9)."""
import time

from .. import db
from ..domain import metrics as rules
from ..errors import not_found
from . import media, moderation, qr, realtime

_last_bytes: dict[str, tuple[float, int]] = {}


def _streams() -> tuple[int, list]:
    paths = media.ready_paths()
    if paths is None:
        with db.tx() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM stream_keys WHERE status = 'active'")
            return int(cur.fetchone()["n"]), []
    now = time.monotonic()
    rates = []
    for p in paths:
        name, received = p.get("name", ""), int(p.get("bytesReceived") or 0)
        prev = _last_bytes.get(name)
        kbps = ((received - prev[1]) * 8 / 1000 / (now - prev[0])) if prev and now > prev[0] else 0.0
        _last_bytes[name] = (now, received)
        rates.append(({"stream": name}, max(0.0, kbps)))
    return len(paths), rates


def render() -> str:
    count, rates = _streams()
    return rules.render({
        "nascon_active_ws_connections": realtime.connection_count(),
        "nascon_active_streams_total": count,
        "nascon_stream_bitrate_kbps": rates,
        "nascon_dlq_depth": moderation.dlq_depth(),
        "nascon_qr_scans_total": qr.total_scans(),
    })


def erase_user(user_id: str) -> dict:
    anon = rules.anon_id(user_id)
    with db.tx() as cur:
        db.lock(cur, "privacy:" + user_id)
        cur.execute("SELECT player_id FROM players WHERE player_id = %s", (user_id,))
        player = cur.fetchone()
        cur.execute("SELECT user_id, player_id FROM users WHERE user_id = %s OR player_id = %s", (user_id, user_id))
        users = cur.fetchall()
        if player is None and not users:
            raise not_found("PLAYER_NOT_FOUND", f"User {user_id} not found.", user_id=user_id)
        ids = {user_id} | {u["user_id"] for u in users} | {u["player_id"] for u in users if u["player_id"]}
        ids = list(ids)
        cur.execute("UPDATE players SET name = %s, profile = '{}' WHERE player_id = ANY(%s)", ("Anonymized athlete", ids))
        for u in users:
            cur.execute("UPDATE users SET email = %s, name = 'Anonymized user', password_hash = '!' WHERE user_id = %s",
                        (f"{rules.anon_id(u['user_id'])}@anon.invalid", u["user_id"]))
        cur.execute("DELETE FROM follows WHERE follower_id = ANY(%s) OR athlete_id = ANY(%s)", (ids, ids))
        cur.execute("UPDATE stream_keys SET status = 'revoked', revoked_at = now() "
                    "WHERE player_id = ANY(%s) AND status = 'active'", (ids,))
        cur.execute("UPDATE guest_tokens SET revoked = TRUE, merged_user_id = %s, cart = '[]' "
                    "WHERE merged_user_id = ANY(%s)", (anon, ids))
        cur.execute("DELETE FROM carts WHERE user_id = ANY(%s)", (ids,))
        cur.execute("UPDATE chat_messages SET sender = %s WHERE sender = ANY(%s)", (anon, ids))
        cur.execute("UPDATE moderation_state SET user_id = %s WHERE user_id = ANY(%s) "
                    "AND NOT EXISTS (SELECT 1 FROM moderation_state m2 WHERE m2.user_id = %s)", (anon, ids, anon))
    return {"user_id": user_id, "status": "anonymized", "pii_retained": False, "tokens_wiped": True}
