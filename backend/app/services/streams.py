"""Stream key lifecycle (spec 5.4) and the MediaMTX publish-auth hook."""
import threading

from .. import config, crypto, db
from ..domain import streaming
from ..errors import conflict, not_found
from . import media


def _bases() -> tuple[str, str, str]:
    return config.MEDIA_RTMP_BASE, config.MEDIA_WEBRTC_BASE, config.MEDIA_HLS_BASE


def player_exists(cur, player_id: str) -> bool:
    cur.execute("SELECT 1 FROM players WHERE player_id = %s", (player_id,))
    return cur.fetchone() is not None


def handle(body: dict) -> tuple[int, dict]:
    req = streaming.validate_request(body)
    action, player_id = req["action"], req["player_id"]
    revoked_key = None
    with db.tx() as cur:
        if not player_exists(cur, player_id):
            raise not_found("PLAYER_NOT_FOUND", f"Player {player_id} not found.", player_id=player_id)
        db.lock(cur, "streamkey:" + player_id)
        if action == "revoke":
            cur.execute("SELECT stream_key, label, status FROM stream_keys WHERE player_id = %s "
                        "ORDER BY (status = 'active') DESC, seq DESC LIMIT 1", (player_id,))
            row = cur.fetchone()
            if row is None:
                raise not_found("STREAM_NOT_FOUND", f"Player {player_id} has no stream key.", player_id=player_id)
            if row["status"] != "active":
                raise conflict("KEY_REVOKED", "The stream key has already been revoked.",
                               stream_key=row["stream_key"])
            cur.execute("UPDATE stream_keys SET status = 'revoked', revoked_at = now() WHERE stream_key = %s",
                        (row["stream_key"],))
            key, label, status, http = row["stream_key"], row["label"], "revoked", 200
            revoked_key = key
        else:
            cur.execute("SELECT stream_key FROM stream_keys WHERE player_id = %s AND status = 'active'", (player_id,))
            old = cur.fetchone()
            if old:
                cur.execute("UPDATE stream_keys SET status = 'rotated', revoked_at = now() WHERE stream_key = %s",
                            (old["stream_key"],))
                revoked_key = old["stream_key"]
            key = req["stream_key_override"] or streaming.new_key()
            label, status = req["label"], "active"
            cur.execute("INSERT INTO stream_keys (stream_key, player_id, label, status) VALUES (%s,%s,%s,'active') "
                        "ON CONFLICT (stream_key) DO UPDATE SET player_id = EXCLUDED.player_id, "
                        "label = EXCLUDED.label, status = 'active', revoked_at = NULL, seq = DEFAULT",
                        (key, player_id, label))
            if revoked_key == key:
                revoked_key = None
            http = 201 if action == "generate" else 200
    if revoked_key:
        # Sever live ingest on the old key (spec 5.4: within 2 s). Off the request path.
        threading.Thread(target=media.kick_path, args=("live/" + revoked_key,), daemon=True).start()
    signature = crypto.sign_day2(key, streaming.sig_payload(action, player_id, status, key))
    return http, streaming.response(action, player_id, label, key, status, _bases(), signature)


def key_status(stream_key: str) -> str | None:
    with db.tx() as cur:
        cur.execute("SELECT status FROM stream_keys WHERE stream_key = %s", (stream_key,))
        row = cur.fetchone()
    return row["status"] if row else None


def check_key(stream_key: str) -> dict:
    status = key_status(stream_key)
    if status is None:
        raise not_found("STREAM_NOT_FOUND", f"Stream key {stream_key} not found.", stream_key=stream_key)
    if status != "active":
        raise conflict("KEY_REVOKED", "This stream key has been revoked.", stream_key=stream_key)
    return {"stream_key": stream_key, "status": "active"}


def authorize_media(action: str, path: str, ip: str | None) -> bool:
    """MediaMTX auth hook: publishing to live/<key> needs an active key; internal paths only from the network."""
    if action != "publish":
        return True
    if path.startswith("live/"):
        return key_status(path[len("live/"):]) == "active"
    if path.startswith(("costream/", "matchfeed/")):
        return ip is None or ip.startswith(("127.", "172.", "10.", "192.168.", "::1"))
    return False
