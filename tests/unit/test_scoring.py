import json
from pathlib import Path

import pytest

from app.crypto import canonical, lots_key, sign
from app.domain import scoring
from app.domain.scoring import Log
from app.domain.sports import validate_sport
from app.errors import ApiError

SPORTS = {s["sport_id"]: s for s in json.loads(
    (Path(__file__).parents[2] / "backend" / "app" / "seed" / "sports.json").read_text(encoding="utf-8"))}


def make_log(sport_id, events, home="h", away="a"):
    match = {"match_id": "m1", "sport_id": sport_id, "league_id": None, "home_team_id": home, "away_team_id": away}
    rows = [{"sequence": i + 1, "event_id": e[0], "type": e[1], "payload": e[2], "signature": "s"}
            for i, e in enumerate(events)]
    return Log(match, SPORTS[sport_id], rows)


def body(eid, type_, payload):
    return {"event_id": eid, "match_id": "m1", "type": type_, "payload": payload}


def err(log, b):
    with pytest.raises(ApiError) as e:
        scoring.check_event(log, b)
    return e.value.code


def test_appendix_a_vectors():
    assert canonical({"team_id": "t1", "event_type": "goal"}) == '{"event_type":"goal","team_id":"t1"}'
    assert sign("evt-1", {"team_id": "t1", "event_type": "goal"}, "demo-salt") == \
        "972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501"
    assert lots_key(42, "lg-1", "t1").startswith("0613316991ce0ac3")
    assert canonical({"b": [1, {"z": None, "a": True}], "é": 1.5}) == '{"b":[1,{"a":true,"z":null}],"é":1.5}'


def test_seed_sports_are_valid():
    for s in SPORTS.values():
        assert validate_sport(s)["sport_id"] == s["sport_id"]


@pytest.mark.parametrize("field,value", [
    ("sport_id", "A"), ("name", ""), ("scoring_model", "x"), ("periods", {"count": 0}),
    ("scoring_events", {}), ("scoring_events", {"Bad-Key": {"points": 1}}), ("draw_allowed", "no"),
    ("overtime", {"policy": "sudden"}), ("tie_break_order", ["h2h_points", "h2h_points"]),
    ("roster", {"min_squad_size": 5, "max_squad_size": 2, "required_positions": {}}),
])
def test_sport_validation(field, value):
    with pytest.raises(ApiError) as e:
        validate_sport(dict(SPORTS["football"], **{field: value}))
    assert field in e.value.details["fields"]


def test_round_and_innings_validation():
    with pytest.raises(ApiError):
        validate_sport(dict(SPORTS["esports"], periods={"best_of": 2}))
    with pytest.raises(ApiError):
        validate_sport(dict(SPORTS["cricket"], scoring_events={"x": {"runs": 1, "legal_ball": "y", "wicket": False}}))
    cfg = validate_sport({k: v for k, v in SPORTS["football"].items() if k != "tie_break_order"})
    assert cfg["tie_break_order"][-1] == "draw_lots"


def test_event_model_projection_and_rules():
    log = make_log("football", [("e1", "match_start", {}),
                                ("e2", "score", {"team_id": "h", "event_type": "goal"}),
                                ("e3", "score", {"team_id": "h", "event_type": "goal"}),
                                ("e4", "discipline", {"team_id": "a", "points": -1}),
                                ("e5", "compensation", {"compensates": "e3", "reason": "offside"})])
    assert log.status == "in_progress"
    assert err(log, body("x", "match_start", {})) == "ILLEGAL_TRANSITION"
    assert err(log, body("x", "score", {"team_id": "z", "event_type": "goal"})) == "VALIDATION_ERROR"
    assert err(log, body("x", "score", {"team_id": "h", "event_type": "try"})) == "UNKNOWN_EVENT_TYPE"
    assert err(log, body("x", "discipline", {"team_id": "h", "points": "1"})) == "VALIDATION_ERROR"
    assert err(log, body("x", "compensation", {"compensates": "e3"})) == "INVALID_COMPENSATION"
    assert err(log, body("x", "compensation", {"compensates": "e1"})) == "INVALID_COMPENSATION"
    assert err(log, body("x", "compensation", {"compensates": "zz"})) == "EVENT_NOT_FOUND"
    assert err(log, body("x", "compensation", {"compensates": ""})) == "VALIDATION_ERROR"
    assert err(log, body("x", "match_init", {})) == "MATCH_EXISTS"
    scoring.check_event(log, body("x", "match_end", {}))
    p = scoring.project(log)
    assert p["home"]["score"] == 1 and p["away"]["fair_play"] == -1 and p["outcome"] == "pending"
    assert p["events"][2]["compensated_by"] == "e5" and p["version"] == 5


def test_outcomes():
    base = [("e1", "match_start", {})]
    done = [("z", "match_end", {})]
    assert scoring.project(make_log("football", base + done))["outcome"] == "draw"
    log = make_log("basketball", base + [("t", "tiebreak_winner", {"team_id": "a"})] + done)
    assert scoring.project(log)["outcome"] == "away_win"
    log = make_log("basketball", base + [("t", "tiebreak_winner", {"team_id": "a"}),
                                         ("c", "compensation", {"compensates": "t"})] + done)
    assert scoring.project(log)["outcome"] == "undecided"
    log = make_log("basketball", base + [("s", "score", {"team_id": "a", "event_type": "three_pointer"})] + done)
    assert scoring.project(log)["winner_team_id"] == "a"
    log = make_log("basketball", base)
    assert err(log, body("x", "match_end", {})) == "TIE_NOT_ALLOWED"
    upcoming = make_log("basketball", [])
    assert err(upcoming, body("x", "match_end", {})) == "ILLEGAL_TRANSITION"
    assert err(upcoming, body("x", "score", {"team_id": "h", "event_type": "free_throw"})) == "MATCH_NOT_IN_PROGRESS"


def test_innings_and_round_limits():
    balls = [(f"b{i}", "score", {"team_id": "h", "event_type": "single"}) for i in range(120)]
    log = make_log("cricket", [("e0", "match_start", {})] + balls)
    assert err(log, body("x", "score", {"team_id": "h", "event_type": "four"})) == "INNINGS_COMPLETE"
    scoring.check_event(log, body("x", "score", {"team_id": "a", "event_type": "four"}))
    p = scoring.project(log)
    assert p["home"]["overs"] == "20.0" and p["home"]["score"] == 120
    log = make_log("esports", [("e0", "match_start", {}),
                               ("r1", "score", {"team_id": "a", "event_type": "round_win"}),
                               ("r2", "score", {"team_id": "a", "event_type": "round_win"})])
    assert err(log, body("x", "score", {"team_id": "h", "event_type": "round_win"})) == "SERIES_ALREADY_DECIDED"


def test_envelope_validation():
    with pytest.raises(ApiError) as e:
        scoring.validate_envelope({"event_id": "a|b", "match_id": "m", "type": "score", "payload": []})
    assert set(e.value.details["fields"]) == {"event_id", "payload"}
    with pytest.raises(ApiError):
        scoring.validate_init_payload({"sport_id": "f", "home_team_id": "x", "away_team_id": "x"})
    with pytest.raises(ApiError):
        scoring.validate_init_payload({"sport_id": "f", "home_team_id": "x", "away_team_id": "y", "league_id": 5})
