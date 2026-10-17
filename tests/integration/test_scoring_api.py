from app.crypto import sign

KABADDI = {
    "sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
    "periods": {"count": 2, "duration_minutes": 20},
    "scoring_events": {"raid_point": {"points": 1}, "tackle_point": {"points": 1}, "all_out": {"points": 2}},
    "draw_allowed": False, "overtime": {"policy": "golden_score", "duration_minutes": 5},
    "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
    "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2, "defender": 3}},
}


def ev(api, eid, mid, type_, payload):
    return api.post("/audit/v1/events", {"event_id": eid, "match_id": mid, "type": type_, "payload": payload})


def test_mystery_sport_full_flow(fresh):
    api = fresh
    r = api.post("/audit/v1/sports", KABADDI)
    assert r.status_code == 201 and r.json()["config"]["sport_id"] == "kabaddi"
    assert api.post("/audit/v1/sports", KABADDI).json()["error"]["code"] == "SPORT_EXISTS"
    bad = dict(KABADDI, sport_id="x'; DROP TABLE sports;--")
    r = api.post("/audit/v1/sports", bad)
    assert r.status_code == 400 and "sport_id" in r.json()["error"]["details"]["fields"]

    r = ev(api, "e1", "k1", "match_init", {"sport_id": "kabaddi", "home_team_id": "a", "away_team_id": "b"})
    assert r.status_code == 201 and r.json()["sequence"] == 1
    assert ev(api, "e1b", "k1", "match_init",
              {"sport_id": "kabaddi", "home_team_id": "a", "away_team_id": "b"}).json()["error"]["code"] == "MATCH_EXISTS"
    assert ev(api, "e2", "k1", "score", {"team_id": "a", "event_type": "all_out"}).json()["error"]["code"] == \
        "MATCH_NOT_IN_PROGRESS"
    assert ev(api, "e2", "k1", "match_start", {}).status_code == 201
    assert ev(api, "e2x", "k1", "match_start", {}).json()["error"]["code"] == "ILLEGAL_TRANSITION"
    r = ev(api, "e3", "k1", "score", {"team_id": "a", "event_type": "all_out"})
    assert r.status_code == 201
    assert r.json()["signature"] == sign("e3", {"team_id": "a", "event_type": "all_out"}, "demo-salt")
    assert ev(api, "e3", "k1", "score", {"team_id": "a", "event_type": "all_out"}).status_code == 200
    assert ev(api, "e3", "k1", "score", {"team_id": "b", "event_type": "all_out"}).json()["error"]["code"] == \
        "DUPLICATE_EVENT_ID"
    assert ev(api, "e4", "k1", "score", {"team_id": "a", "event_type": "goal"}).json()["error"]["code"] == \
        "UNKNOWN_EVENT_TYPE"
    assert ev(api, "e4", "k1", "score", {"team_id": "zz", "event_type": "all_out"}).status_code == 400
    assert ev(api, "e4", "k1", "score", {"team_id": "b", "event_type": "all_out"}).status_code == 201
    assert ev(api, "e5", "k1", "match_end", {}).json()["error"]["code"] == "TIE_NOT_ALLOWED"
    assert ev(api, "e5", "k1", "tiebreak_winner", {"team_id": "b"}).status_code == 201
    assert ev(api, "e6", "k1", "match_end", {}).status_code == 201
    s = api.get("/audit/v1/score/k1").json()
    assert s["status"] == "completed" and s["outcome"] == "away_win" and s["winner_team_id"] == "b"
    assert ev(api, "e7", "k1", "compensation", {"compensates": "e5", "reason": "review"}).status_code == 201
    s = api.get("/audit/v1/score/k1").json()
    assert s["outcome"] == "undecided" and s["winner_team_id"] is None and s["version"] == 7
    assert s["events"][4]["compensated"] is True and s["events"][4]["compensated_by"] == "e7"
    assert ev(api, "e8", "k1", "compensation", {"compensates": "e5", "reason": "x"}).json()["error"]["code"] == \
        "INVALID_COMPENSATION"
    assert ev(api, "e8", "k1", "compensation", {"compensates": "e2", "reason": "x"}).json()["error"]["code"] == \
        "INVALID_COMPENSATION"
    assert ev(api, "e8", "k1", "compensation", {"compensates": "nope", "reason": "x"}).json()["error"]["code"] == \
        "EVENT_NOT_FOUND"
    assert ev(api, "e9", "missing", "match_start", {}).json()["error"]["code"] == "MATCH_NOT_FOUND"
    assert api.get("/audit/v1/score/missing").status_code == 404


def test_innings_limits_and_overs(fresh):
    api = fresh
    sport = {"sport_id": "mini_cricket", "name": "Mini", "scoring_model": "innings",
             "periods": {"innings_per_team": 1, "overs_per_innings": 1, "balls_per_over": 6, "wickets_per_innings": 2},
             "scoring_events": {"super_six": {"runs": 6, "legal_ball": True, "wicket": False},
                                "bye_run": {"runs": 1, "legal_ball": False, "wicket": False},
                                "out": {"runs": 0, "legal_ball": True, "wicket": True}},
             "draw_allowed": True, "overtime": {"policy": "super_over"},
             "roster": {"min_squad_size": 2, "max_squad_size": 5, "required_positions": {}}}
    assert api.post("/audit/v1/sports", sport).status_code == 201
    ev(api, "c0", "c1", "match_init", {"sport_id": "mini_cricket", "home_team_id": "h", "away_team_id": "a"})
    ev(api, "c1", "c1", "match_start", {})
    assert ev(api, "c2", "c1", "score", {"team_id": "h", "event_type": "super_six"}).status_code == 201
    assert ev(api, "c3", "c1", "score", {"team_id": "h", "event_type": "bye_run"}).status_code == 201
    assert ev(api, "c4", "c1", "score", {"team_id": "h", "event_type": "out"}).status_code == 201
    assert ev(api, "c5", "c1", "score", {"team_id": "h", "event_type": "out"}).status_code == 201
    assert ev(api, "c6", "c1", "score", {"team_id": "h", "event_type": "super_six"}).json()["error"]["code"] == \
        "INNINGS_COMPLETE"
    ev(api, "c7", "c1", "compensation", {"compensates": "c5", "reason": "no ball"})
    assert ev(api, "c8", "c1", "score", {"team_id": "h", "event_type": "super_six"}).status_code == 201
    s = api.get("/audit/v1/score/c1").json()
    assert s["home"] == {"team_id": "h", "score": 13, "wickets": 1, "balls": 3, "overs": "0.3", "fair_play": 0}
    assert s["away"]["overs"] == "0.0"


def test_round_series_decided(fresh):
    api = fresh
    ev(api, "r0", "s1", "match_init", {"sport_id": "esports", "home_team_id": "h", "away_team_id": "a"})
    ev(api, "r1", "s1", "match_start", {})
    assert ev(api, "r2", "s1", "score", {"team_id": "h", "event_type": "round_win"}).status_code == 201
    assert ev(api, "r3", "s1", "score", {"team_id": "h", "event_type": "round_win"}).status_code == 201
    assert ev(api, "r4", "s1", "score", {"team_id": "a", "event_type": "round_win"}).json()["error"]["code"] == \
        "SERIES_ALREADY_DECIDED"
    assert ev(api, "r5", "s1", "discipline", {"team_id": "a", "points": -2}).status_code == 201
    ev(api, "r6", "s1", "match_end", {})
    s = api.get("/audit/v1/score/s1").json()
    assert s["outcome"] == "home_win" and s["home"]["score"] == 2 and s["away"]["fair_play"] == -2
    assert s["home"]["wickets"] is None


def test_validation_and_limits(fresh):
    api = fresh
    r = api.post("/audit/v1/events", {"event_id": "x", "match_id": "m", "type": "bogus", "payload": {}})
    assert r.status_code == 400 and r.json()["error"]["details"]["fields"] == ["type"]
    r = api.s.post(api.base + "/audit/v1/sports", data="{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    r = api.s.post(api.base + "/audit/v1/sports", data="x" * (1024 * 1024 + 10),
                   headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
