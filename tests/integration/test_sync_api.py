from app.crypto import sign

from .test_roster_api import SETUP, tr


def ev(api, eid, mid, type_, payload):
    return api.post("/audit/v1/events", {"event_id": eid, "match_id": mid, "type": type_, "payload": payload})


def score_action(aid, eid, base, queued, team="h", mid="m1"):
    return {"action_id": aid, "type": "score_event", "queued_at": queued, "base_version": base,
            "payload": {"event_id": eid, "match_id": mid, "type": "score",
                        "payload": {"team_id": team, "event_type": "goal"}}}


def test_offline_sync_resolution_table(fresh):
    api = fresh
    ev(api, "i1", "m1", "match_init", {"sport_id": "football", "home_team_id": "h", "away_team_id": "a"})
    ev(api, "i2", "m1", "match_start", {})
    ev(api, "i3", "m1", "score", {"team_id": "a", "event_type": "goal"})
    api.post("/audit/v1/roster/setup", SETUP)
    body = {"device_id": "dev-1", "actions": [
        score_action("a1", "evt-9", 3, "2026-10-17T11:00:00Z"),           # applied / appended (version 3)
        score_action("a0", "evt-8", 1, "2026-10-17T10:59:00Z"),           # processed first: stale -> rebased
        score_action("a3", "evt-10", 99, "2026-10-17T11:02:00Z"),         # INVALID_BASE_VERSION
        score_action("a4", "evt-11", 0, "2026-10-17T11:03:00Z", team="zz"),  # rule -> VALIDATION_ERROR
        score_action("a5", "evt-12", 0, "2026-10-17T11:04:00Z", mid="ghost"),  # MATCH_NOT_FOUND
        {"action_id": "a2", "type": "roster_transfer", "queued_at": "2026-10-17T11:01:00Z", "base_version": 0,
         "payload": tr("tr-s1", "p2", "transfer", "sq-a", "sq-b")},     # applied roster
        {"action_id": "a6", "type": "roster_transfer", "queued_at": "2026-10-17T11:05:00Z", "base_version": 1,
         "payload": tr("tr-s2", "p2", "transfer", "sq-a", "sq-b")},     # NOT_IN_SQUAD (already moved)
    ]}
    r = api.post("/audit/v1/offline-sync", body)
    assert r.status_code == 200, r.text
    res = {x["action_id"]: x for x in r.json()["results"]}
    assert [x["action_id"] for x in r.json()["results"]] == ["a1", "a0", "a3", "a4", "a5", "a2", "a6"]
    assert res["a0"]["status"] == "applied" and res["a0"]["resolution"] == "rebased_append"
    assert res["a0"]["processed_order"] == 1 and res["a0"]["server_version"] == 4
    assert res["a1"]["resolution"] == "appended" or res["a1"]["resolution"] == "rebased_append"
    assert res["a1"]["signature"] == sign("evt-9", {"team_id": "h", "event_type": "goal"}, "demo-salt")
    assert res["a3"]["error_code"] == "INVALID_BASE_VERSION" and res["a3"]["status"] == "rejected"
    assert res["a4"]["error_code"] == "VALIDATION_ERROR"
    assert res["a5"]["error_code"] == "MATCH_NOT_FOUND"
    assert res["a2"]["status"] == "applied" and res["a2"]["signature"] is None and res["a2"]["server_version"] == 1
    assert res["a6"]["error_code"] == "NOT_IN_SQUAD" and res["a6"]["resolution"] == "server_wins"
    assert r.json()["summary"] == {"applied": 3, "rejected": 4, "duplicate": 0}

    again = api.post("/audit/v1/offline-sync", body).json()
    assert all(x["status"] == "duplicate" and x["resolution"] == "skipped_duplicate" for x in again["results"])
    assert again["summary"] == {"applied": 0, "rejected": 0, "duplicate": 7}
    assert api.get("/audit/v1/score/m1").json()["version"] == 5

    # Same event_id already on the server with an identical payload -> duplicate.
    other = {"device_id": "dev-2", "actions": [score_action("b1", "evt-9", 5, "2026-10-17T12:00:00Z")]}
    assert api.post("/audit/v1/offline-sync", other).json()["results"][0]["status"] == "duplicate"
    assert api.post("/audit/v1/offline-sync", {"device_id": "d", "actions": []}).status_code == 400
