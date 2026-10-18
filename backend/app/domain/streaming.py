"""Creator stream keys (FR-3.2, spec 5.4): request validation, key format, signed response."""
import re
import secrets

from ..errors import validation
from .validate import is_id

ACTIONS = ("generate", "rotate", "revoke")
KEY_RE = re.compile(r"^sk_live_[a-f0-9]{16}$")


def validate_request(body: dict) -> dict:
    bad = []
    action = body.get("action")
    if action not in ACTIONS:
        bad.append("action")
    if not is_id(body.get("player_id")):
        bad.append("player_id")
    label = body.get("label", "default")
    if label is None:
        label = "default"
    if not isinstance(label, str) or not (1 <= len(label) <= 64):
        bad.append("label")
    override = body.get("stream_key_override")
    if override is not None and (not isinstance(override, str) or not (1 <= len(override) <= 128)
                                 or not re.match(r"^[A-Za-z0-9_\-]+$", override)):
        bad.append("stream_key_override")
    if bad:
        raise validation(bad)
    return {"action": action, "player_id": body["player_id"], "label": label, "stream_key_override": override}


def new_key() -> str:
    return "sk_live_" + secrets.token_hex(8)


def endpoints(stream_key: str, rtmp_base: str, webrtc_base: str, hls_base: str) -> tuple[dict, str]:
    ingest = {"rtmp": f"{rtmp_base}/live/{stream_key}", "webrtc": f"{webrtc_base}/live/{stream_key}/whip"}
    return ingest, f"{hls_base}/live/{stream_key}/index.m3u8"


def sig_payload(action: str, player_id: str, status: str, stream_key: str) -> dict:
    return {"action": action, "player_id": player_id, "status": status, "stream_key": stream_key}


def response(action: str, player_id: str, label: str, stream_key: str, status: str, bases: tuple[str, str, str],
             signature: str) -> dict:
    if status == "active":
        ingest, playback = endpoints(stream_key, *bases)
    else:
        ingest, playback = None, None
    return {"player_id": player_id, "label": label, "stream_key": stream_key, "status": status,
            "ingest_endpoints": ingest, "playback_url": playback, "signature": signature}
