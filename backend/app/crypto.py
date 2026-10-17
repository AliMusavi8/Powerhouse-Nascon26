"""Canonical JSON, HMAC signatures (spec 5.3) and drawing-of-lots keys (spec 5.10)."""
import hashlib
import hmac
import json

from . import config


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(id_: str, payload_obj, salt: str | None = None) -> str:
    key = (config.DAY1_SALT if salt is None else salt).encode("utf-8")
    msg = (id_ + "|" + canonical(payload_obj)).encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def lots_key(seed: int, league_id: str, team_id: str) -> str:
    return hashlib.sha256(f"{seed}|{league_id}|{team_id}".encode("utf-8")).hexdigest()


def body_hash(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()
