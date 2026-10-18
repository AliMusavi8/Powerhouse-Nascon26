"""Pure Phase II domain modules: streaming, costream, qr, guest, moderation, dlq, metrics."""
from datetime import datetime, timezone

import pytest

from app.domain import costream, dlq, guest, metrics, moderation, qr, streaming
from app.errors import ApiError


def code_of(fn, *args):
    with pytest.raises(ApiError) as e:
        fn(*args)
    return e.value.code


# ---------------------------------------------------------------- streaming

def test_stream_request_validation():
    ok = streaming.validate_request({"action": "rotate", "player_id": "p1"})
    assert ok == {"action": "rotate", "player_id": "p1", "label": "default", "stream_key_override": None}
    assert streaming.validate_request({"action": "generate", "player_id": "p1", "label": None})["label"] == "default"
    for bad in ({"action": "x", "player_id": "p1"}, {"action": "rotate"}, {"action": "rotate", "player_id": "p1",
                                                                           "label": ""},
                {"action": "rotate", "player_id": "p1", "label": "x" * 65},
                {"action": "rotate", "player_id": "p1", "stream_key_override": "bad key"},
                {"action": "rotate", "player_id": "p1", "stream_key_override": 5}):
        assert code_of(streaming.validate_request, bad) == "VALIDATION_ERROR"


def test_stream_key_format_and_response():
    key = streaming.new_key()
    assert streaming.KEY_RE.match(key)
    bases = ("rtmp://h:1935", "http://h:8889", "http://h:8888")
    active = streaming.response("rotate", "p1", "default", key, "active", bases, "sig")
    assert active["ingest_endpoints"]["rtmp"] == f"rtmp://h:1935/live/{key}"
    assert active["ingest_endpoints"]["webrtc"] == f"http://h:8889/live/{key}/whip"
    assert active["playback_url"] == f"http://h:8888/live/{key}/index.m3u8"
    revoked = streaming.response("revoke", "p1", "default", key, "revoked", bases, "sig")
    assert revoked["ingest_endpoints"] is None and revoked["playback_url"] is None
    assert list(streaming.sig_payload("rotate", "p1", "active", key)) == ["action", "player_id", "status",
                                                                          "stream_key"]


# ---------------------------------------------------------------- costream

PLAYERS = {"a", "b", "c", "d", "e"}


def req(parts, host="a", drop=False, layout="grid_4", sid="cs-1"):
    return costream.validate_schema({"session_id": sid, "host_player_id": host, "participants": parts,
                                     "simulate_host_drop": drop, "layout": layout})


def test_costream_schema():
    assert costream.validate_schema({"session_id": "s", "host_player_id": "a", "participants": ["a"]})["layout"] == \
        "grid_4"
    assert costream.validate_schema({"session_id": "s", "host_player_id": "a", "participants": ["a"],
                                     "layout": None, "simulate_host_drop": None})["simulate_host_drop"] is False
    for bad in ({"host_player_id": "a", "participants": ["a"]}, {"session_id": "s", "participants": ["a"]},
                {"session_id": "s", "host_player_id": "a", "participants": []},
                {"session_id": "s", "host_player_id": "a", "participants": ["a", "a"]},
                {"session_id": "s", "host_player_id": "a", "participants": ["a"], "layout": "pip"},
                {"session_id": "s", "host_player_id": "a", "participants": ["a"], "simulate_host_drop": "yes"}):
        assert code_of(costream.validate_schema, bad) == "VALIDATION_ERROR"


def test_costream_order_of_checks():
    assert code_of(costream.evaluate, req(["a", "zz"]), PLAYERS) == "PLAYER_NOT_FOUND"
    assert code_of(costream.evaluate, req(["b"], host="a"), PLAYERS) == "VALIDATION_ERROR"
    assert code_of(costream.evaluate, req(["a", "b", "c", "d", "e"]), PLAYERS) == "COSTREAM_SESSION_FULL"
    assert code_of(costream.evaluate, req(["a", "b"], layout="solo"), PLAYERS) == "UNSUPPORTED_LAYOUT"
    assert code_of(costream.evaluate, req(["a", "b", "c"], layout="grid_2"), PLAYERS) == "UNSUPPORTED_LAYOUT"
    # the effective count after a host drop is what must fit
    assert costream.evaluate(req(["a", "b"], drop=True, layout="solo"), PLAYERS)["active_host"] == "b"
    assert costream.evaluate(req(["a", "b", "c"], drop=True, layout="grid_2"), PLAYERS)["participant_count"] == 2


def test_costream_handoff_table():
    assert costream.evaluate(req(["a", "b", "c", "d"]), PLAYERS) == {
        "status": "active", "active_host": "a", "handoff_occurred": False, "participant_count": 4,
        "active_participants": ["a", "b", "c", "d"], "layout": "grid_4"}
    assert costream.evaluate(req(["a", "b", "c", "d"], drop=True), PLAYERS) == {
        "status": "active", "active_host": "b", "handoff_occurred": True, "participant_count": 3,
        "active_participants": ["b", "c", "d"], "layout": "grid_4"}
    assert costream.evaluate(req(["c", "a", "b"], drop=True), PLAYERS)["active_host"] == "c"
    assert costream.evaluate(req(["a"], drop=True, layout="solo"), PLAYERS) == {
        "status": "terminated", "active_host": None, "handoff_occurred": False, "participant_count": 0,
        "active_participants": [], "layout": "solo"}
    assert costream.effective_count(1, True) == 0 and costream.effective_count(3, False) == 3


def test_costream_response_shape():
    state = costream.handoff("a", ["a", "b"], True, "spotlight")
    r = costream.response("cs-9", state, "http://h:8888", "sig")
    assert r["composite_playback_url"] == "http://h:8888/costream/cs-9/index.m3u8"
    assert r["chat_room_id"] == "chat-cs-9"
    assert costream.sig_payload("cs-9", state) == {"active_host": "b", "handoff_occurred": True,
                                                    "layout": "spotlight", "participant_count": 1,
                                                    "session_id": "cs-9", "status": "active"}


# ---------------------------------------------------------------- qr

@pytest.mark.parametrize("kind,status,route", [
    ("match", "upcoming", "/web/matches/m/preview"), ("match", "in_progress", "/web/matches/m/live"),
    ("match", "completed", "/web/matches/m/vod"), ("match", "postponed", "/web/matches/m/notice?state=postponed"),
    ("match", "cancelled", "/web/matches/m/notice?state=cancelled"),
    ("match", "abandoned", "/web/matches/m/notice?state=abandoned"), ("player", "active", "/web/players/m"),
    ("club", "active", "/web/clubs/m"), ("costream", "active", "/web/costream/m")])
def test_target_routes(kind, status, route):
    assert qr.target_route(kind, "m", status) == route


def test_qr_helpers():
    assert qr.short_code("match-9", "salt") == qr.short_code("match-9", "salt")
    assert qr.short_code("match-9", "salt") != qr.short_code("match-9", "other") and len(qr.short_code("x", "")) == 8
    assert qr.device_family("Mozilla/5.0 (Linux; Android 13) Mobile Safari") == "mobile"
    assert qr.device_family("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)") == "mobile"
    assert qr.device_family("Mozilla/5.0 (X11; Linux x86_64) Chrome/130") == "desktop"
    assert qr.device_family(None) == "desktop"
    assert qr.bucket(datetime(2026, 10, 18, 9, 41, tzinfo=timezone.utc)) == "2026-10-18T09:00Z"
    assert qr.bucket().endswith(":00Z")
    v = qr.view("match-m1", "match", "in_progress", "http://h/q/m1-live", "/web/matches/match-m1/live", 3,
                "http://h", "sig")
    assert v["export_formats"]["svg"] == "http://h/audit/v1/qr/match-m1/export.svg"
    assert v["deep_link_uri"] == "nascon://entity/match-m1" and v["scan_count"] == 3
    assert qr.sig_payload("e", "u", "r") == {"entity_id": "e", "short_url": "u", "target_route": "r"}


# ---------------------------------------------------------------- guest

def test_guest_write_rejection():
    assert guest.bearer("Bearer guest_anon_tok_1") == "guest_anon_tok_1"
    assert guest.bearer("Basic x") is None and guest.bearer(None) is None and guest.bearer("Bearer ") is None
    err = guest.write_rejection("POST", "/api/v1/chat", "guest_anon_tok_1")
    assert err.status == 403 and err.code == "GUEST_WRITE_FORBIDDEN" and err.details == {"guest_token":
                                                                                          "guest_anon_tok_1"}
    assert guest.write_rejection("DELETE", "/audit/v1/x", "guest_x").status == 403
    assert guest.write_rejection("GET", "/api/v1/chat", "guest_x") is None
    assert guest.write_rejection("POST", "/api/v1/chat", "eyJhbGciOi") is None
    assert guest.write_rejection("POST", "/api/v1/guest/cart/", "guest_x") is None
    assert guest.write_rejection("POST", "/api/v1/guest/session", "guest_x") is None


def test_cart_merge_validation():
    ok = guest.validate_cart_merge({"guest_token": "guest_1", "registered_user_id": "p1",
                                    "guest_cart": [{"variant_id": "v", "quantity": 2}]})
    assert ok["test_write_block"] is True
    assert guest.validate_cart_merge({"guest_token": "guest_1", "registered_user_id": "p1", "test_write_block": None,
                                      "guest_cart": [{"variant_id": "v", "quantity": 1}]})["test_write_block"] is True
    base = {"guest_token": "guest_1", "registered_user_id": "p1", "guest_cart": [{"variant_id": "v", "quantity": 1}]}
    for patch in ({"guest_token": "tok"}, {"guest_token": None}, {"registered_user_id": ""}, {"guest_cart": []},
                  {"guest_cart": [{"variant_id": "v", "quantity": 0}] * 1}, {"guest_cart": ["x"]},
                  {"guest_cart": [{"variant_id": "v", "quantity": 1}] * 11}, {"test_write_block": "no"}):
        assert code_of(guest.validate_cart_merge, dict(base, **patch)) == "VALIDATION_ERROR"


def test_cart_merge_math():
    assert guest.combine([{"variant_id": "a", "quantity": 1}, {"variant_id": "b", "quantity": 2},
                          {"variant_id": "a", "quantity": 3}]) == {"a": 4, "b": 2}
    assert guest.merge({"a": 1}, {"a": 2, "b": 1}, {"a": 5, "b": 1}) == {"a": 3, "b": 1}
    assert code_of(guest.merge, {"a": 4}, {"a": 2}, {"a": 5}) == "OUT_OF_STOCK"
    assert code_of(guest.merge, {}, {"z": 1}, {}) == "OUT_OF_STOCK"
    view = guest.cart_view("p1", {"a": 2, "b": 1}, {"a": 100, "b": 50})
    assert view == {"user_id": "p1", "currency": "PKR", "total_items": 3, "subtotal_minor": 250,
                    "items": [{"variant_id": "a", "quantity": 2, "unit_price_minor": 100},
                              {"variant_id": "b", "quantity": 1, "unit_price_minor": 50}]}
    assert guest.is_guest_token("guest_x") and not guest.is_guest_token(None)


# ---------------------------------------------------------------- moderation

@pytest.mark.parametrize("text,masked", [
    ("Watch this illegal stream b@d_w0rd now!", "Watch this illegal stream *** now!"),
    ("that bad_word again", "that *** again"), ("p.0.r.n link", "*** link"), ("total s!c@m", "total ***"),
    ("f*u*c*k this", "*** this"), ("you a$$h0le", "you ***"), ("sh1t happens", "*** happens"),
    ("(scam)", "(***)"), ("BITCH.", "***."), ("idiot_spam bot", "*** bot"), ("b​ad​word", "***"),
])
def test_leetspeak_masking(text, masked):
    assert moderation.mask(text) == (masked, True)


@pytest.mark.parametrize("text", ["Clean sports commentary", "Live reaction", "What a save by the keeper!",
                                  "illegal offside", "Pass it 1 2 3", "GOAL!"])
def test_clean_messages(text):
    assert moderation.mask(text) == (text, False) and not moderation.is_flood(text)


@pytest.mark.parametrize("text", ["GOAL! AAAA!!!", "noooooo", "AaAa wow", "what???", "!!!", "????"])
def test_flood_detection(text):
    assert moderation.is_flood(text)


def test_moderate_batch_spec_example_and_rate_limit():
    out = moderation.moderate([
        {"message_id": "1", "sender": "g", "text": "Clean sports commentary"},
        {"message_id": "2", "sender": "s", "text": "Watch this illegal stream b@d_w0rd now!"},
        {"message_id": "3", "sender": "f", "text": "GOAL! AAAA!!!"},
        {"message_id": "4", "sender": "s", "text": "more sc@m"},
        {"message_id": "5", "sender": "f", "text": "AAAA"},
    ])
    assert [m["message_id"] for m in out["filtered_messages"]] == ["1", "2", "4"]
    assert out["kicked_users"] == ["s"] and out["muted_users"] == ["f"] and out["flagged_count"] == 2
    burst = moderation.moderate([{"message_id": str(i), "sender": "r", "text": "hi"} for i in range(5)])
    assert len(burst["filtered_messages"]) == 3 and burst["muted_users"] == ["r"]


def test_moderation_validation_and_classify():
    ok = moderation.validate_request({"chat_room_id": "r", "incoming_messages": []})
    assert ok["check_dlq"] is True and ok["simulate_failed_notifications"] == 0
    assert moderation.validate_request({"chat_room_id": "r", "incoming_messages": [], "check_dlq": None,
                                        "simulate_failed_notifications": None})["check_dlq"] is True
    for bad in ({"incoming_messages": []}, {"chat_room_id": "r"}, {"chat_room_id": "r", "incoming_messages": [{}]},
                {"chat_room_id": "r", "incoming_messages": [], "check_dlq": 1},
                {"chat_room_id": "r", "incoming_messages": [], "simulate_failed_notifications": -1}):
        assert code_of(moderation.validate_request, bad) == "VALIDATION_ERROR"
    assert moderation.classify("hello") == (None, "hello")
    assert moderation.classify("go sc@m") == ("profanity_leetspeak", "go ***")
    assert moderation.classify("AAAAH")[0] == "flood_character_repeat"
    assert moderation.sig_payload("r", 1, ["s"], 0) == {"chat_room_id": "r", "flagged_count": 1,
                                                        "kicked_users": ["s"], "queue_depth": 0}


# ---------------------------------------------------------------- dlq

def test_dlq_retry_and_dead_letter():
    assert dlq.backoff_schedule() == [0.1, 0.2]
    waits = []
    calls = []
    assert dlq.deliver(calls.append, {"x": 1}, sleep=waits.append) == (True, 1, None)
    def boom(_):
        raise ConnectionError("down")
    assert dlq.deliver(boom, {}, sleep=waits.append) == (False, 3, "down")
    assert waits == [0.1, 0.2]
    assert dlq.deliver(calls.append, {"simulate_dlq": True})[0] is False
    e = dlq.dead_letter("t", "push:r", {}, 3, "err", "2026-10-18T10:00:00Z")
    assert e["event_id"].startswith("evt-") and dlq.public(e) == {
        "event_id": e["event_id"], "type": "t", "target": "push:r", "attempts": 3, "last_error": "err",
        "failed_at": "2026-10-18T10:00:00Z"}


# ---------------------------------------------------------------- metrics

def test_metrics_render():
    text = metrics.render({"nascon_dlq_depth": 2, "nascon_qr_scans_total": 7,
                           "nascon_stream_bitrate_kbps": [({"stream": 'live/"k"'}, 2500.4567)]})
    assert "# TYPE nascon_qr_scans_total counter\nnascon_qr_scans_total 7" in text
    assert "nascon_dlq_depth 2" in text and "nascon_active_ws_connections 0" in text
    assert 'nascon_stream_bitrate_kbps{stream="live/\\"k\\""} 2500.457' in text
    assert "nascon_stream_bitrate_kbps 0" in metrics.render({"nascon_stream_bitrate_kbps": []})
    assert text.endswith("\n") and metrics.CONTENT_TYPE == "text/plain; version=0.0.4"
    assert metrics.anon_id("player-alpha-1").startswith("anon-") and len(metrics.anon_id("x")) == 13


# ---------------------------------------------------------------- match notice states (dynamic QR re-routing)

def test_notice_events_drive_match_status():
    from app.domain import scoring
    sport = {"scoring_model": "event", "scoring_events": {"goal": {"points": 1}}, "draw_allowed": True,
             "periods": {}}
    match = {"match_id": "m", "home_team_id": "h", "away_team_id": "a", "sport_id": "s"}

    def log(*types, payloads=None):
        payloads = payloads or [{}] * len(types)
        return scoring.Log(match, sport, [{"sequence": i + 1, "event_id": f"e{i}", "type": t, "payload": p,
                                           "signature": ""} for i, (t, p) in enumerate(zip(types, payloads))])

    def check(lg, type_, payload=None):
        scoring.check_event(lg, {"match_id": "m", "event_id": "x", "type": type_, "payload": payload or {}})

    assert log("match_start", "match_postponed").status == "postponed"
    assert log("match_cancelled").status == "cancelled"
    assert log("match_start", "match_status", payloads=[{}, {"status": "abandoned"}]).status == "abandoned"
    assert scoring.notice_state("match_status", {"status": "weird"}) is None
    check(log(), "match_postponed")
    check(log("match_start"), "match_status", {"status": "cancelled"})
    check(log("match_postponed"), "match_start")
    assert code_of(check, log("match_start"), "match_status", {"status": "done"}) == "VALIDATION_ERROR"
    assert code_of(check, log("match_start", "match_end"), "match_postponed") == "ILLEGAL_TRANSITION"
    assert code_of(check, log("match_cancelled"), "match_start") == "ILLEGAL_TRANSITION"
