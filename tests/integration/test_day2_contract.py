"""Part II contract (spec section 5) against the live stack. Signatures are recomputed independently."""
import hashlib
import hmac
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

DAY2_SALT = os.environ.get("DAY2_SALT", "T01D27ad7ffff12e")
GUEST = "guest_anon_tok_7721"


def sig(entity_id, payload):
    msg = entity_id + "|" + json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(DAY2_SALT.encode(), msg.encode(), hashlib.sha256).hexdigest()


def err(r):
    return r.json()["error"]["code"]


# ---------------------------------------------------------------- 5.2 reset seed

def test_reset_seeds_phase_two_baseline(fresh):
    score = fresh.get("/audit/v1/score/match-m1").json()
    assert score["status"] == "in_progress" and score["home"]["team_id"] == "club-alpha-1"
    assert (score["home"]["score"], score["away"]["score"]) == (1, 0)
    for entity, code in (("match-m1", "m1-live"), ("player-alpha-1", "p-alpha-1"), ("club-alpha-1", "c-alpha-1")):
        body = fresh.get(f"/audit/v1/qr/{entity}?inspect=true").json()
        assert body["short_url"] == f"http://localhost:8080/q/{code}" and body["scan_count"] == 0
    assert fresh.post("/audit/v1/costream/session", {"session_id": "cs-x", "host_player_id": "player-beta-2",
                                                     "participants": ["player-beta-2"]}).status_code == 201


def test_guest_direct_writes_are_forbidden(fresh):
    for path in ("/api/v1/chat", "/audit/v1/checkout", "/audit/v1/events"):
        r = fresh.post(path, {"chat_room_id": "chat-cs-session-101", "text": "hi"},
                       headers={"Authorization": f"Bearer {GUEST}"})
        assert r.status_code == 403 and err(r) == "GUEST_WRITE_FORBIDDEN"
        assert r.json()["error"]["details"]["guest_token"] == GUEST


# ---------------------------------------------------------------- 5.4 stream keys

def test_stream_key_lifecycle(fresh):
    body = {"action": "rotate", "player_id": "player-alpha-1", "label": "OBS-Main-Desk",
            "stream_key_override": "sk_live_9f83a1b2c3d4e5f6"}
    r = fresh.post("/audit/v1/stream/key", body)
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"player_id", "label", "stream_key", "status", "ingest_endpoints", "playback_url", "signature"}
    assert d["stream_key"] == "sk_live_9f83a1b2c3d4e5f6" and d["status"] == "active" and d["label"] == "OBS-Main-Desk"
    assert d["ingest_endpoints"] == {"rtmp": "rtmp://localhost:1935/live/sk_live_9f83a1b2c3d4e5f6",
                                     "webrtc": "http://localhost:8889/live/sk_live_9f83a1b2c3d4e5f6/whip"}
    assert d["playback_url"] == "http://localhost:8888/live/sk_live_9f83a1b2c3d4e5f6/index.m3u8"
    assert d["signature"] == sig(d["stream_key"], {"action": "rotate", "player_id": "player-alpha-1",
                                                   "status": "active", "stream_key": d["stream_key"]})

    g = fresh.post("/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-1"})
    assert g.status_code == 201 and g.json()["label"] == "default"
    assert g.json()["stream_key"].startswith("sk_live_") and len(g.json()["stream_key"]) == 24

    v = fresh.post("/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-1"})
    assert v.status_code == 200
    vd = v.json()
    assert vd["status"] == "revoked" and vd["ingest_endpoints"] is None and vd["playback_url"] is None
    assert vd["signature"] == sig(vd["stream_key"], {"action": "revoke", "player_id": "player-alpha-1",
                                                     "status": "revoked", "stream_key": vd["stream_key"]})
    again = fresh.post("/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-1"})
    assert again.status_code == 409 and err(again) == "KEY_REVOKED"
    assert err(fresh.get(f"/api/v1/streams/key/{vd['stream_key']}")) == "KEY_REVOKED"


def test_stream_key_errors(fresh):
    assert err(fresh.post("/audit/v1/stream/key", {"action": "pause", "player_id": "player-alpha-1"})) == \
        "VALIDATION_ERROR"
    assert err(fresh.post("/audit/v1/stream/key", {"action": "rotate", "player_id": "nobody"})) == "PLAYER_NOT_FOUND"
    r = fresh.post("/audit/v1/stream/key", {"action": "revoke", "player_id": "player-beta-1"})
    assert r.status_code == 404 and err(r) == "STREAM_NOT_FOUND"


# ---------------------------------------------------------------- 5.5 co-stream

COSTREAM = {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
            "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"],
            "layout": "grid_4", "simulate_host_drop": True}


def test_costream_host_drop_and_replay(fresh):
    r = fresh.post("/audit/v1/costream/session", COSTREAM)
    assert r.status_code == 201
    d = r.json()
    assert d == {"session_id": "cs-session-101", "status": "active", "active_host": "player-alpha-2",
                 "handoff_occurred": True, "participant_count": 3,
                 "active_participants": ["player-alpha-2", "player-beta-1", "player-beta-2"], "layout": "grid_4",
                 "composite_playback_url": "http://localhost:8888/costream/cs-session-101/index.m3u8",
                 "chat_room_id": "chat-cs-session-101", "signature": d["signature"]}
    assert d["signature"] == sig("cs-session-101", {"active_host": "player-alpha-2", "handoff_occurred": True,
                                                    "layout": "grid_4", "participant_count": 3,
                                                    "session_id": "cs-session-101", "status": "active"})
    replay = fresh.post("/audit/v1/costream/session", COSTREAM)
    assert replay.status_code == 200 and replay.json() == d


def test_costream_live_session_then_host_drop_keeps_chat(fresh):
    live = dict(COSTREAM, simulate_host_drop=False)
    a = fresh.post("/audit/v1/costream/session", live).json()
    assert a["active_host"] == "player-alpha-1" and a["handoff_occurred"] is False and a["participant_count"] == 4
    b = fresh.post("/audit/v1/costream/session", COSTREAM).json()
    assert b["active_host"] == "player-alpha-2" and b["chat_room_id"] == a["chat_room_id"]
    assert b["composite_playback_url"] == a["composite_playback_url"]


def test_costream_rules_in_order(fresh):
    base = {"session_id": "cs-r", "host_player_id": "player-alpha-1"}
    assert err(fresh.post("/audit/v1/costream/session", dict(base, participants=[]))) == "VALIDATION_ERROR"
    assert err(fresh.post("/audit/v1/costream/session", dict(base, participants=["player-alpha-1", "ghost"]))) == \
        "PLAYER_NOT_FOUND"
    r = fresh.post("/audit/v1/costream/session", dict(base, participants=["player-alpha-2"]))
    assert r.status_code == 400 and err(r) == "VALIDATION_ERROR"
    five = ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2", "demo-p1"]
    with_demo = fresh.get("/audit/v1/score/match-m1")  # warm
    assert with_demo.status_code == 200
    r = fresh.post("/audit/v1/costream/session", dict(base, participants=five))
    assert err(r) in ("COSTREAM_SESSION_FULL", "PLAYER_NOT_FOUND")
    r = fresh.post("/audit/v1/costream/session", dict(base, participants=COSTREAM["participants"], layout="grid_2"))
    assert r.status_code == 400 and err(r) == "UNSUPPORTED_LAYOUT"
    solo = fresh.post("/audit/v1/costream/session", {"session_id": "cs-solo", "host_player_id": "player-alpha-1",
                                                     "participants": ["player-alpha-1"], "simulate_host_drop": True})
    assert solo.status_code == 201
    assert solo.json()["status"] == "terminated" and solo.json()["active_host"] is None
    assert solo.json()["participant_count"] == 0 and solo.json()["handoff_occurred"] is False


def test_costream_session_full(fresh):
    r = fresh.post("/audit/v1/reset", {})
    assert r.status_code == 200
    from_db = fresh.post("/audit/v1/costream/session", {
        "session_id": "cs-full", "host_player_id": "player-alpha-1",
        "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2", "player-alpha-1x"]})
    assert err(from_db) == "PLAYER_NOT_FOUND"


# ---------------------------------------------------------------- 5.6 QR

def test_qr_resolution_scan_count_and_mutation(fresh):
    d = fresh.get("/audit/v1/qr/match-m1").json()
    assert d["entity_type"] == "match" and d["entity_status"] == "in_progress" and d["scan_count"] == 1
    assert d["target_route"] == "/web/matches/match-m1/live" and d["deep_link_uri"] == "nascon://entity/match-m1"
    assert d["export_formats"]["pdf"] == "http://localhost:8080/audit/v1/qr/match-m1/export.pdf"
    assert d["signature"] == sig("match-m1", {"entity_id": "match-m1", "short_url": "http://localhost:8080/q/m1-live",
                                              "target_route": "/web/matches/match-m1/live"})
    assert fresh.get("/audit/v1/qr/match-m1?inspect=true").json()["scan_count"] == 1

    r = fresh.s.get(fresh.base + "/q/m1-live", allow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/web/matches/match-m1/live"

    end = fresh.post("/audit/v1/events", {"event_id": "m1-end-" + uuid.uuid4().hex[:6], "match_id": "match-m1",
                                          "type": "match_end", "payload": {}})
    assert end.status_code == 201
    after = fresh.get("/audit/v1/qr/match-m1?inspect=true").json()
    assert after["short_url"] == d["short_url"] and after["target_route"] == "/web/matches/match-m1/vod"
    assert after["signature"] != d["signature"] and after["scan_count"] == 2


def test_qr_postponed_notice(fresh):
    r = fresh.post("/audit/v1/events", {"event_id": "m1-pp", "match_id": "match-m1", "type": "match_postponed",
                                        "payload": {}})
    assert r.status_code == 201
    d = fresh.get("/audit/v1/qr/match-m1?inspect=true").json()
    assert d["entity_status"] == "postponed"
    assert d["target_route"] == "/web/matches/match-m1/notice?state=postponed"


def test_qr_other_entities_and_exports(fresh):
    assert fresh.get("/audit/v1/qr/player-alpha-1").json()["target_route"] == "/web/players/player-alpha-1"
    assert fresh.get("/audit/v1/qr/club-alpha-1").json()["target_route"] == "/web/clubs/club-alpha-1"
    lazy = fresh.get("/audit/v1/qr/club-alpha-2").json()
    assert lazy["short_url"].startswith("http://localhost:8080/q/") and lazy["scan_count"] == 1
    r = fresh.get("/audit/v1/qr/nope")
    assert r.status_code == 404 and err(r) == "QR_NOT_FOUND"
    svg = fresh.get("/audit/v1/qr/match-m1/export.svg")
    assert svg.headers["content-type"].startswith("image/svg+xml") and svg.text.lstrip().startswith(("<?xml", "<svg"))
    png = fresh.get("/audit/v1/qr/match-m1/export.png")
    assert png.headers["content-type"] == "image/png" and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    pdf = fresh.get("/audit/v1/qr/match-m1/export.pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF-")
    assert err(fresh.get("/audit/v1/qr/nope/export.png")) == "QR_NOT_FOUND"


# ---------------------------------------------------------------- 5.7 guest cart merge

MERGE = {"guest_token": GUEST, "registered_user_id": "player-alpha-1",
         "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "test_write_block": True}


def test_cart_merge_and_network_replay(fresh):
    r = fresh.post("/audit/v1/guest/cart-merge", MERGE)
    assert r.status_code == 200
    d = r.json()
    assert d["write_block_verified"] is True and d["write_rejection_code"] == 403 and d["cart_merged"] is True
    assert d["active_cart"] == {"user_id": "player-alpha-1", "currency": "PKR", "total_items": 1,
                                "subtotal_minor": 450000, "items": [{"variant_id": "var-jersey-001-L", "quantity": 1,
                                                                     "unit_price_minor": 450000}]}
    assert d["signature"] == sig(GUEST, {"cart_merged": True, "guest_token": GUEST,
                                         "registered_user_id": "player-alpha-1", "total_items": 1,
                                         "write_rejection_code": 403})
    replay = fresh.post("/audit/v1/guest/cart-merge", MERGE)
    assert replay.status_code == 200 and replay.json()["active_cart"]["total_items"] == 1
    other = fresh.post("/audit/v1/guest/cart-merge", dict(MERGE, registered_user_id="player-alpha-2"))
    assert other.status_code == 409 and err(other) == "GUEST_TOKEN_ALREADY_MERGED"
    assert fresh.get("/audit/v1/inventory/var-jersey-001-L").json()["stock"] == 5


def test_cart_merge_concurrent_replays_never_double_add(fresh):
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: requests.post(fresh.base + "/audit/v1/guest/cart-merge", json=MERGE,
                                                        timeout=15), range(8)))
    assert all(r.status_code == 200 for r in results)
    assert {r.json()["active_cart"]["total_items"] for r in results} == {1}


def test_cart_merge_errors(fresh):
    assert err(fresh.post("/audit/v1/guest/cart-merge", dict(MERGE, guest_token="anon"))) == "VALIDATION_ERROR"
    assert err(fresh.post("/audit/v1/guest/cart-merge", dict(MERGE, registered_user_id="ghost"))) == "PLAYER_NOT_FOUND"
    assert err(fresh.post("/audit/v1/guest/cart-merge", dict(MERGE, guest_cart=[{"variant_id": "var-x",
                                                                               "quantity": 1}]))) == "VARIANT_NOT_FOUND"
    r = fresh.post("/audit/v1/guest/cart-merge", dict(MERGE, guest_token="guest_t2",
                                                      guest_cart=[{"variant_id": "var-jersey-001-M", "quantity": 2}]))
    assert r.status_code == 409 and err(r) == "OUT_OF_STOCK"
    assert r.json()["error"]["details"]["variant_id"] == "var-jersey-001-M"


# ---------------------------------------------------------------- 5.8 moderation + DLQ

MOD = {"chat_room_id": "chat-cs-session-101", "check_dlq": True, "simulate_failed_notifications": 0,
       "incoming_messages": [
           {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary"},
           {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream b@d_w0rd now!"},
           {"message_id": "msg-3", "sender": "user-flooder", "text": "GOAL! AAAA!!!"}]}


def test_moderation_spec_example(fresh):
    r = fresh.post("/audit/v1/moderation/test", MOD)
    assert r.status_code == 200
    d = r.json()
    assert d["filtered_messages"] == [
        {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary", "flagged": False,
         "reason": None},
        {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream *** now!", "flagged": True,
         "reason": "profanity_leetspeak"}]
    assert d["kicked_users"] == ["user-spammer"] and d["muted_users"] == ["user-flooder"]
    assert d["dlq_status"] == {"queue_depth": 0, "undelivered_events": []}
    assert d["signature"] == sig("chat-cs-session-101", {"chat_room_id": "chat-cs-session-101", "flagged_count": 1,
                                                         "kicked_users": ["user-spammer"], "queue_depth": 0})


def test_moderation_dual_moderator_race_and_dlq(fresh):
    with ThreadPoolExecutor(10) as pool:
        results = list(pool.map(lambda _: requests.post(fresh.base + "/audit/v1/moderation/test", json=MOD,
                                                        timeout=15), range(10)))
    assert all(r.status_code == 200 for r in results)
    assert all(r.json()["kicked_users"] == ["user-spammer"] for r in results)
    d = fresh.post("/audit/v1/moderation/test", dict(MOD, simulate_failed_notifications=3)).json()
    assert d["dlq_status"]["queue_depth"] == 3 and len(d["dlq_status"]["undelivered_events"]) == 3
    assert d["dlq_status"]["undelivered_events"][0]["attempts"] == 3
    m = fresh.get("/metrics")
    assert "nascon_dlq_depth 3" in m.text


# ---------------------------------------------------------------- 5.9 metrics + privacy

def test_metrics_format(fresh):
    r = fresh.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"] == "text/plain; version=0.0.4"
    for name in ("nascon_active_ws_connections", "nascon_active_streams_total", "nascon_stream_bitrate_kbps",
                 "nascon_dlq_depth", "nascon_qr_scans_total"):
        assert f"# TYPE {name} " in r.text
    fresh.get("/audit/v1/qr/match-m1")
    assert "nascon_qr_scans_total 1" in fresh.get("/metrics").text


def test_privacy_erasure(fresh):
    fresh.post("/audit/v1/guest/cart-merge", MERGE)
    r = fresh.s.delete(fresh.base + "/audit/v1/privacy/user/player-alpha-1", timeout=15)
    assert r.status_code == 200
    assert r.json() == {"user_id": "player-alpha-1", "status": "anonymized", "pii_retained": False,
                        "tokens_wiped": True}
    missing = fresh.s.delete(fresh.base + "/audit/v1/privacy/user/ghost", timeout=15)
    assert missing.status_code == 404
