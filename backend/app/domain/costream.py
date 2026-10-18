"""Synchronized 4-way co-streaming (FR-3.3, spec 5.5). Validation in the contract's exact order + host handoff."""
from ..errors import ApiError, not_found, validation
from .validate import is_id

LAYOUTS = ("solo", "grid_2", "grid_4", "spotlight")
MAX_BROADCASTERS = 4


def validate_schema(body: dict) -> dict:
    bad = []
    if not is_id(body.get("session_id")):
        bad.append("session_id")
    if not is_id(body.get("host_player_id")):
        bad.append("host_player_id")
    parts = body.get("participants")
    if (not isinstance(parts, list) or not parts or not all(is_id(p) for p in parts)
            or len(set(parts)) != len(parts)):
        bad.append("participants")
    drop = body.get("simulate_host_drop", False)
    if drop is None:
        drop = False
    if not isinstance(drop, bool):
        bad.append("simulate_host_drop")
    layout = body.get("layout", "grid_4")
    if layout is None:
        layout = "grid_4"
    if layout not in LAYOUTS:
        bad.append("layout")
    if bad:
        raise validation(bad)
    return {"session_id": body["session_id"], "host_player_id": body["host_player_id"], "participants": parts,
            "simulate_host_drop": drop, "layout": layout}


def check_players(req: dict, existing: set[str]) -> None:
    for pid in [req["host_player_id"], *req["participants"]]:
        if pid not in existing:
            raise not_found("PLAYER_NOT_FOUND", f"Player {pid} not found.", player_id=pid)
    if req["host_player_id"] not in req["participants"]:
        raise validation("host_player_id", "host_player_id must be one of the participants.")


def effective_count(n: int, drop: bool) -> int:
    if not drop:
        return n
    return n - 1 if n >= 2 else 0


def evaluate(req: dict, existing: set[str]) -> dict:
    """Run steps 2-5 of spec 5.5 on a schema-valid request. Returns the session state."""
    check_players(req, existing)
    parts, drop, layout = req["participants"], req["simulate_host_drop"], req["layout"]
    if len(parts) > MAX_BROADCASTERS:
        raise ApiError(409, "COSTREAM_SESSION_FULL", "A co-stream supports at most 4 broadcasters.",
                       {"max_participants": MAX_BROADCASTERS, "requested": len(parts)})
    eff = effective_count(len(parts), drop)
    if (layout == "solo" and eff > 1) or (layout == "grid_2" and eff > 2):
        raise ApiError(400, "UNSUPPORTED_LAYOUT", f"Layout {layout} cannot fit {eff} active participants.",
                       {"layout": layout, "active_participants": eff})
    return handoff(req["host_player_id"], parts, drop, layout)


def handoff(host: str, parts: list[str], drop: bool, layout: str) -> dict:
    if not drop:
        return {"status": "active", "active_host": host, "handoff_occurred": False,
                "participant_count": len(parts), "active_participants": list(parts), "layout": layout}
    remaining = [p for p in parts if p != host]
    if remaining:
        return {"status": "active", "active_host": remaining[0], "handoff_occurred": True,
                "participant_count": len(parts) - 1, "active_participants": remaining, "layout": layout}
    return {"status": "terminated", "active_host": None, "handoff_occurred": False, "participant_count": 0,
            "active_participants": [], "layout": layout}


def sig_payload(session_id: str, state: dict) -> dict:
    return {"active_host": state["active_host"], "handoff_occurred": state["handoff_occurred"],
            "layout": state["layout"], "participant_count": state["participant_count"], "session_id": session_id,
            "status": state["status"]}


def response(session_id: str, state: dict, hls_base: str, signature: str) -> dict:
    return {"session_id": session_id, "status": state["status"], "active_host": state["active_host"],
            "handoff_occurred": state["handoff_occurred"], "participant_count": state["participant_count"],
            "active_participants": state["active_participants"], "layout": state["layout"],
            "composite_playback_url": f"{hls_base}/costream/{session_id}/index.m3u8",
            "chat_room_id": f"chat-{session_id}", "signature": signature}
