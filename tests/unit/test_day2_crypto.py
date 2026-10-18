"""Appendix A (Part II) signature vectors."""
import hashlib
import hmac

from app.crypto import canonical, sign_day2

SALT = "T01D27ad7ffff12e"


def reference(salt, entity_id, payload):
    msg = (entity_id + "|" + canonical(payload)).encode("utf-8")
    return hmac.new(salt.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def test_vector_1_stream_key_four_keys():
    payload = {"action": "rotate", "player_id": "player-alpha-1", "status": "active",
               "stream_key": "sk_live_9f83a1b2c3d4e5f6"}
    assert canonical(payload) == ('{"action":"rotate","player_id":"player-alpha-1","status":"active",'
                                  '"stream_key":"sk_live_9f83a1b2c3d4e5f6"}')
    sig = sign_day2("sk_live_9f83a1b2c3d4e5f6", payload, SALT)
    assert sig == reference(SALT, "sk_live_9f83a1b2c3d4e5f6", payload)
    assert len(sig) == 64 and sig == sig.lower()


def test_vector_2_legacy_two_keys():
    payload = {"action": "rotate", "player_id": "player-alpha-1"}
    assert "sk_live_101|" + canonical(payload) == 'sk_live_101|{"action":"rotate","player_id":"player-alpha-1"}'
    assert sign_day2("sk_live_101", payload, SALT) == reference(SALT, "sk_live_101", payload)


def test_default_salt_comes_from_config(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DAY2_SALT", SALT)
    assert sign_day2("x", {"a": 1}) == reference(SALT, "x", {"a": 1})
