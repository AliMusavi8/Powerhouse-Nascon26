import json
from pathlib import Path

from app.domain.standings import Table, result_from_projection

SPORTS = {s["sport_id"]: s for s in json.loads(
    (Path(__file__).parents[2] / "backend" / "app" / "seed" / "sports.json").read_text(encoding="utf-8"))}
TBO = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]


def cfg(teams, spots=2, tbo=TBO, lots_seed=42, league_id="lg-1"):
    return {"league_id": league_id, "teams": teams, "points": {"win": 3, "draw": 1, "loss": 0},
            "tie_break_order": tbo, "spots": spots, "lots_seed": lots_seed}


def res(h, a, hs, as_, hf=0, af=0, played=True, hb=0, ab=0, hw=0, aw=0):
    result = "home" if hs > as_ else "away" if as_ > hs else "draw"
    return {"home": h, "away": a, "played": played, "result": result if played else None,
            "hs": hs, "as": as_, "hf": hf, "af": af, "hb": hb, "ab": ab, "hw": hw, "aw": aw}


def test_three_way_mini_league():
    results = [res("t1", "t2", 1, 0), res("t2", "t3", 1, 0), res("t3", "t1", 3, 0),
               res("t1", "t4", 1, 0), res("t2", "t4", 1, 0), res("t3", "t4", 1, 0)]
    out = Table(cfg(["t1", "t2", "t3", "t4"]), SPORTS["football"], results).compute()
    order = [r["team_id"] for r in out["table"]]
    assert order == ["t3", "t2", "t1", "t4"]
    by = {r["team_id"]: r["resolved_by"] for r in out["table"]}
    assert by == {"t3": "h2h_diff", "t2": "h2h_diff", "t1": None, "t4": None}
    assert out["h2h"]["t3"]["t1"] == {"played": 1, "points": 3, "scored": 3, "conceded": 0}
    assert out["h2h"]["t4"]["t1"]["points"] == 0
    t3 = out["table"][0]
    assert (t3["played"], t3["won"], t3["lost"], t3["points"], t3["diff"]) == (3, 2, 1, 6, 3)


def test_restart_on_split_and_draw_lots():
    # All draws 0-0: every criterion equal, so draw_lots decides (Appendix A vector 2: t1, t3, t2).
    results = [res("t1", "t2", 0, 0), res("t2", "t3", 0, 0), res("t1", "t3", 0, 0)]
    out = Table(cfg(["t1", "t2", "t3"], spots=1), SPORTS["football"], results).compute()
    assert [r["team_id"] for r in out["table"]] == ["t1", "t3", "t2"]
    assert out["table"][0]["resolved_by"] == "draw_lots"


def test_fair_play_and_scored_criteria():
    results = [res("a", "b", 2, 2, hf=0, af=-3), res("c", "d", 1, 1)]
    out = Table(cfg(["a", "b", "c", "d"], tbo=["fair_play"]), SPORTS["football"], results).compute()
    order = [r["team_id"] for r in out["table"]]
    assert order.index("a") < order.index("b")
    out = Table(cfg(["a", "b", "c", "d"], tbo=["scored"]), SPORTS["football"], results).compute()
    order = [r["team_id"] for r in out["table"]]
    assert order[:2] in (["a", "b"], ["b", "a"]) and out["table"][0]["resolved_by"] in ("scored", "draw_lots")


def test_qualification_status():
    teams = ["t1", "t2", "t3", "t4"]
    results = [res("t1", "t2", 1, 0), res("t1", "t3", 1, 0), res("t1", "t4", 1, 0),
               res("t2", "t3", 1, 0), res("t2", "t4", 0, 0, played=False), res("t3", "t4", 0, 0, played=False)]
    out = Table(cfg(teams, spots=1), SPORTS["football"], results).compute()
    st = {r["team_id"]: r["status"] for r in out["table"]}
    assert st["t1"] == "clinched"
    assert st["t3"] == "eliminated"
    assert st["t4"] == "still_possible" or st["t4"] == "eliminated"
    out = Table(cfg(teams, spots=2), SPORTS["football"], results).compute()
    st = {r["team_id"]: r["status"] for r in out["table"]}
    assert st["t1"] == "clinched" and st["t2"] == "still_possible"


def test_net_run_rate():
    # Home: 120 runs off 20 overs; away all out (10 wickets) for 100 in 15 overs => counted as 20 overs.
    results = [res("h", "a", 120, 100, hb=120, ab=90, hw=3, aw=10)]
    out = Table(cfg(["h", "a"], spots=1), SPORTS["cricket"], results).compute()
    rows = {r["team_id"]: r for r in out["table"]}
    assert rows["h"]["diff"] == 1.0 and rows["a"]["diff"] == -1.0
    results = [res("h", "a", 100, 101, hb=120, ab=100, hw=5, aw=4)]
    out = Table(cfg(["h", "a"], spots=1), SPORTS["cricket"], results).compute()
    rows = {r["team_id"]: r for r in out["table"]}
    assert rows["a"]["diff"] == round(101 / (100 / 6) - 100 / 20, 3)


def test_round_model_diff():
    results = [res("x", "y", 2, 1)]
    out = Table(cfg(["x", "y"], spots=1), SPORTS["esports"], results).compute()
    assert out["table"][0]["diff"] == 1


def test_result_from_projection():
    fx = {"home": "h", "away": "a"}
    assert result_from_projection(fx, None)["played"] is False
    proj = {"status": "completed", "outcome": "away_win",
            "home": {"score": 1, "fair_play": 0, "balls": None, "wickets": None},
            "away": {"score": 1, "fair_play": -1, "balls": None, "wickets": None}}
    r = result_from_projection(fx, proj)
    assert r["played"] and r["result"] == "away" and r["af"] == -1
    assert result_from_projection(fx, dict(proj, outcome="undecided"))["played"] is False
