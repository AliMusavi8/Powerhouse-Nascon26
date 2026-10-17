def ev(api, eid, mid, type_, payload):
    r = api.post("/audit/v1/events", {"event_id": eid, "match_id": mid, "type": type_, "payload": payload})
    assert r.status_code in (200, 201), r.text
    return r


def play(api, mid, home_goals, away_goals, home="t1", away="t2"):
    ev(api, f"{mid}-s", mid, "match_start", {})
    for i in range(home_goals):
        ev(api, f"{mid}-h{i}", mid, "score", {"team_id": home, "event_type": "goal"})
    for i in range(away_goals):
        ev(api, f"{mid}-a{i}", mid, "score", {"team_id": away, "event_type": "goal"})
    ev(api, f"{mid}-e", mid, "match_end", {})


def test_league_standings_with_compensation(fresh):
    api = fresh
    body = {"league_id": "lg-1", "sport_id": "football", "teams": ["t1", "t2", "t3", "t4"],
            "fixtures": [{"match_id": "m1", "home": "t1", "away": "t2"}, {"match_id": "m2", "home": "t2", "away": "t3"},
                         {"match_id": "m3", "home": "t3", "away": "t1"}, {"match_id": "m4", "home": "t1", "away": "t4"},
                         {"match_id": "m5", "home": "t2", "away": "t4"}, {"match_id": "m6", "home": "t3", "away": "t4"}],
            "qualification": {"spots": 2}, "lots_seed": 42}
    r = api.post("/audit/v1/leagues", body)
    assert r.status_code == 201 and r.json() == {"league_id": "lg-1", "status": "created", "team_count": 4,
                                                 "fixture_count": 6}
    assert api.post("/audit/v1/leagues", body).json()["error"]["code"] == "LEAGUE_EXISTS"
    assert api.post("/audit/v1/leagues", dict(body, league_id="lg-2")).json()["error"]["code"] == "MATCH_EXISTS"
    assert api.post("/audit/v1/leagues", dict(body, league_id="lg-3", sport_id="nope")).json()["error"]["code"] == \
        "SPORT_NOT_FOUND"
    assert api.post("/audit/v1/leagues", dict(body, qualification={"spots": 9})).status_code == 400

    play(api, "m1", 1, 0, "t1", "t2")
    play(api, "m2", 1, 0, "t2", "t3")
    play(api, "m3", 3, 0, "t3", "t1")
    play(api, "m4", 1, 0, "t1", "t4")
    play(api, "m5", 1, 0, "t2", "t4")
    play(api, "m6", 1, 0, "t3", "t4")
    s = api.get("/audit/v1/standings/lg-1").json()
    assert [r["team_id"] for r in s["table"]] == ["t3", "t2", "t1", "t4"]
    assert s["table"][0]["resolved_by"] == "h2h_diff" and s["qualification_spots"] == 2

    # Disallow one of t3's goals against t1: the mini-league h2h_diff changes and is recomputed from scratch.
    ev(api, "fix-1", "m3", "compensation", {"compensates": "m3-h0", "reason": "offside"})
    ev(api, "fix-2", "m3", "compensation", {"compensates": "m3-h1", "reason": "offside"})
    s = api.get("/audit/v1/standings/lg-1").json()
    t3 = [r for r in s["table"] if r["team_id"] == "t3"][0]
    assert t3["scored"] == 2 and t3["diff"] == 1
    assert [r["team_id"] for r in s["table"]][:3] == ["t1", "t3", "t2"]  # all criteria level -> draw_lots
    assert s["table"][0]["resolved_by"] == "draw_lots"
    assert api.get("/audit/v1/standings/nope").json()["error"]["code"] == "LEAGUE_NOT_FOUND"
    score = api.get("/audit/v1/score/m3").json()
    assert score["league_id"] == "lg-1" and score["events"][1]["compensated"] is True
