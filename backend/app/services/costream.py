"""Co-stream sessions (spec 5.5): persisted state machine with idempotent replay and live host handoff."""
import threading

from .. import config, crypto, db
from ..db import J
from ..domain import costream as rules
from . import media, realtime


def _existing_players(cur, ids: list[str]) -> set[str]:
    cur.execute("SELECT player_id FROM players WHERE player_id = ANY(%s)", (ids,))
    return {r["player_id"] for r in cur.fetchall()}


def _finish(session_id: str, state: dict) -> dict:
    signature = crypto.sign_day2(session_id, rules.sig_payload(session_id, state))
    return rules.response(session_id, state, config.MEDIA_HLS_BASE, signature)


def handle(body: dict) -> tuple[int, dict]:
    req = rules.validate_schema(body)
    sid = req["session_id"]
    digest = crypto.body_hash(req)
    with db.tx() as cur:
        state = rules.evaluate(req, _existing_players(cur, [req["host_player_id"], *req["participants"]]))
        db.lock(cur, "costream:" + sid)
        cur.execute("SELECT body_hash, response FROM costream_sessions WHERE session_id = %s", (sid,))
        prior = cur.fetchone()
        if prior and prior["body_hash"] == digest:
            return 200, prior["response"]
        state["host_player_id"], state["participants"] = req["host_player_id"], req["participants"]
        response = _finish(sid, state)
        cur.execute("INSERT INTO costream_sessions (session_id, body_hash, state, response) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (session_id) DO UPDATE SET body_hash = EXCLUDED.body_hash, state = EXCLUDED.state, "
                    "response = EXCLUDED.response, updated_at = now()", (sid, digest, J(state), J(response)))
        cur.execute("INSERT INTO chat_rooms (chat_room_id) VALUES (%s) ON CONFLICT DO NOTHING", ("chat-" + sid,))
        cur.execute("INSERT INTO qr_codes (entity_id, entity_type, short_code) VALUES (%s,'costream',%s) "
                    "ON CONFLICT DO NOTHING", (sid, _code(sid)))
    _changed(sid, response)
    return (200 if prior else 201), response


def _code(entity_id: str) -> str:
    from ..domain.qr import short_code
    return short_code(entity_id, config.DAY2_SALT)


def _changed(sid: str, response: dict) -> None:
    from . import qr
    qr.invalidate()
    realtime.publish("costream:" + sid, dict(response, type="costream_updated"))
    # Restart the compositor so the composite reflects the new host / layout (MediaMTX re-runs it on demand).
    threading.Thread(target=media.kick_path, args=("costream/" + sid,), daemon=True).start()


def host_disconnected(sid: str, player_id: str) -> dict | None:
    """Live host drop (WebSocket closed): hand hosting to the next participant in array order."""
    with db.tx() as cur:
        db.lock(cur, "costream:" + sid)
        cur.execute("SELECT state FROM costream_sessions WHERE session_id = %s", (sid,))
        row = cur.fetchone()
        if row is None or row["state"]["status"] != "active" or row["state"]["active_host"] != player_id:
            return None
        old = row["state"]
        state = rules.handoff(player_id, old["active_participants"], True, old["layout"])
        state["host_player_id"], state["participants"] = old["host_player_id"], old["participants"]
        response = _finish(sid, state)
        cur.execute("UPDATE costream_sessions SET state = %s, response = %s, body_hash = '', updated_at = now() "
                    "WHERE session_id = %s", (J(state), J(response), sid))
    _changed(sid, response)
    return response


def get(sid: str) -> dict | None:
    with db.tx() as cur:
        cur.execute("SELECT state, response FROM costream_sessions WHERE session_id = %s", (sid,))
        return cur.fetchone()


def layout(sid: str) -> dict | None:
    """For the compositor: active participants with their live stream keys."""
    with db.tx() as cur:
        cur.execute("SELECT state FROM costream_sessions WHERE session_id = %s", (sid,))
        row = cur.fetchone()
        if row is None or row["state"]["status"] != "active":
            return None
        parts = row["state"]["active_participants"]
        cur.execute("SELECT player_id, stream_key FROM stream_keys WHERE status = 'active' AND player_id = ANY(%s)",
                    (parts,))
        keys = {r["player_id"]: r["stream_key"] for r in cur.fetchall()}
    return {"session_id": sid, "layout": row["state"]["layout"], "active_host": row["state"]["active_host"],
            "participants": [{"player_id": p, "stream_key": keys.get(p)} for p in parts]}
