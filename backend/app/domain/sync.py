"""Offline sync envelope validation and conflict-resolution outcomes (spec 5.14)."""
import re

from ..errors import validation
from .validate import is_id, is_int

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ACTION_TYPES = ("score_event", "roster_transfer")


def validate_envelope(body: dict) -> list[dict]:
    if not is_id(body.get("device_id")):
        raise validation("device_id")
    actions = body.get("actions")
    if not isinstance(actions, list) or not (1 <= len(actions) <= 100):
        raise validation("actions")
    seen = set()
    for a in actions:
        if (not isinstance(a, dict) or not is_id(a.get("action_id")) or a.get("type") not in ACTION_TYPES
                or not isinstance(a.get("queued_at"), str) or not TS_RE.match(a["queued_at"])
                or not is_int(a.get("base_version")) or a["base_version"] < 0
                or not isinstance(a.get("payload"), dict) or a["action_id"] in seen):
            raise validation("actions")
        seen.add(a["action_id"])
    return actions


def processing_order(actions: list[dict]) -> list[int]:
    """Indices sorted by queued_at ascending; ties keep array order (stable sort)."""
    return sorted(range(len(actions)), key=lambda i: actions[i]["queued_at"])


def result(action_id: str, status: str, resolution: str, error_code, order: int, version: int, signature=None) -> dict:
    return {"action_id": action_id, "status": status, "resolution": resolution, "error_code": error_code,
            "processed_order": order, "server_version": version, "signature": signature}


def summarize(results: list[dict]) -> dict:
    return {"applied": sum(r["status"] == "applied" for r in results),
            "rejected": sum(r["status"] == "rejected" for r in results),
            "duplicate": sum(r["status"] == "duplicate" for r in results)}
