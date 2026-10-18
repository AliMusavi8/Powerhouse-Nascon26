"""FR-3.1 follow graph + profile, FR-3.2 member stream key, FR-3.3 host controls."""
from concurrent.futures import ThreadPoolExecutor

import requests


def login(api, email):
    token = api.post("/api/v1/auth/login", {"email": email, "password": "Nascon@26"}).json()["token"]
    return {"Authorization": "Bearer " + token}


def test_follow_toggle_burst_has_no_drift(fresh):
    viewer = login(fresh, "viewer@nascon.test")
    url = fresh.base + "/api/v1/players/player-alpha-2/follow"

    def toggle(i):
        method = requests.post if i % 2 == 0 else requests.delete
        return method(url, headers=viewer, timeout=10).status_code

    with ThreadPoolExecutor(16) as pool:
        assert set(pool.map(toggle, range(40))) == {200}
    final = fresh.post("/api/v1/players/player-alpha-2/follow", headers=viewer).json()
    assert final["following"] is True and final["follower_count"] == 1
    again = fresh.post("/api/v1/players/player-alpha-2/follow", headers=viewer).json()
    assert again["follower_count"] == 1  # idempotent per (follower, athlete)
    profile = fresh.get("/api/v1/players/player-alpha-2/profile", headers=viewer).json()
    assert profile["follower_count"] == 1 and profile["following"] is True
    assert profile["affiliations"][0]["club_id"] == "club-alpha-2" and "career" in profile
    un = fresh.s.delete(url, headers=viewer, timeout=10).json()
    assert un["following"] is False and un["follower_count"] == 0
    guest = fresh.post("/api/v1/players/player-alpha-2/follow", headers={"Authorization": "Bearer guest_anon_tok_7721"})
    assert guest.status_code == 403 and guest.json()["error"]["code"] == "GUEST_WRITE_FORBIDDEN"


def test_member_stream_key(fresh):
    player = login(fresh, "player@nascon.test")
    r = fresh.post("/api/v1/streams/key", {"action": "generate", "label": "Phone"}, headers=player)
    assert r.status_code == 201 and r.json()["player_id"] == "player-alpha-1" and r.json()["status"] == "active"
    viewer = login(fresh, "viewer@nascon.test")
    assert fresh.post("/api/v1/streams/key", {"action": "generate"}, headers=viewer).status_code == 403


def test_host_controls(fresh):
    fresh.post("/audit/v1/costream/session", {"session_id": "cs-ctl", "host_player_id": "player-alpha-1",
                                              "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1"]})
    host = login(fresh, "player@nascon.test")
    inv = fresh.post("/api/v1/costream/cs-ctl/invite", {"player_id": "player-beta-2"}, headers=host).json()
    assert inv["invite_token"].startswith("inv_") and inv["deep_link"] == "nascon://stream/cs-ctl"
    muted = fresh.post("/api/v1/costream/cs-ctl/control", {"action": "mute", "player_id": "player-alpha-2"},
                       headers=host).json()
    assert muted["muted"] == ["player-alpha-2"]
    spot = fresh.post("/api/v1/costream/cs-ctl/control", {"action": "spotlight", "player_id": "player-beta-1"},
                      headers=host).json()
    assert spot["layout"] == "spotlight" and spot["active_participants"][0] == "player-beta-1"
    kicked = fresh.post("/api/v1/costream/cs-ctl/control", {"action": "kick", "player_id": "player-alpha-2"},
                        headers=host).json()
    assert "player-alpha-2" not in kicked["active_participants"] and kicked["participant_count"] == 2
    viewer = login(fresh, "viewer@nascon.test")
    r = fresh.post("/api/v1/costream/cs-ctl/control", {"action": "kick", "player_id": "player-beta-1"}, headers=viewer)
    assert r.status_code == 403


def test_failed_notification_retries_then_dead_letters(fresh):
    import uuid
    before = fresh.post("/audit/v1/moderation/test", {"chat_room_id": "r", "incoming_messages": []}).json()
    r = fresh.post("/audit/v1/events", {"event_id": "dlq-" + uuid.uuid4().hex[:8], "match_id": "match-m1",
                                        "type": "score", "payload": {"team_id": "club-alpha-1", "event_type": "goal"},
                                        "simulate_dlq": True})
    assert r.status_code == 201
    after = fresh.post("/audit/v1/moderation/test", {"chat_room_id": "r", "incoming_messages": []}).json()
    assert after["dlq_status"]["queue_depth"] == before["dlq_status"]["queue_depth"] + 1
    last = after["dlq_status"]["undelivered_events"][-1]
    assert last["type"] == "score_update" and last["attempts"] == 3 and last["target"] == "match:match-m1"
