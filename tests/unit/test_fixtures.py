import random
from collections import Counter

import pytest

from app.domain.fixtures import generate
from app.domain.fixtures.elimination import seed_order
from app.domain.fixtures.swiss import min_cost_pairing
from app.errors import ApiError


def teams(n):
    return [f"t{i}" for i in range(1, n + 1)]


@pytest.mark.parametrize("n", range(2, 41))
@pytest.mark.parametrize("legs", [1, 2])
def test_round_robin_properties(n, legs):
    r = generate({"format": "round_robin", "teams": teams(n), "params": {"legs": legs}})
    per_leg = n - 1 if n % 2 == 0 else n
    assert r["round_count"] == per_leg * legs
    pairs, ordered = Counter(), Counter()
    for leg in range(1, legs + 1):
        home, away, byes = Counter(), Counter(), Counter()
        for rd in r["rounds"]:
            ms = [m for m in rd["matches"] if m["leg"] == leg]
            if not ms:
                continue
            assert len(ms) == n // 2
            seen = [x for m in ms for x in (m["home"], m["away"])] + rd["byes"]
            assert sorted(seen) == sorted(teams(n))
            assert len(rd["byes"]) == n % 2
            byes.update(rd["byes"])
            for m in ms:
                home[m["home"]] += 1
                away[m["away"]] += 1
                pairs[frozenset((m["home"], m["away"]))] += 1
                ordered[(m["home"], m["away"])] += 1
        for t in teams(n):
            assert abs(home[t] - away[t]) <= 1
            if n % 2:
                assert byes[t] == 1
    assert len(pairs) == n * (n - 1) // 2 and set(pairs.values()) == {legs}
    if legs == 2:
        assert set(ordered.values()) == {1}


def test_round_robin_ids_and_withdrawals():
    r = generate({"format": "round_robin", "teams": teams(5),
                  "params": {"withdrawals": [{"team_id": "t3", "after_round": 2}]}})
    assert r["rounds"][0]["byes"] == ["t1"]
    assert r["rounds"][0]["matches"][0]["match_id"] == "RR-L1-R1-M1"
    for rd in r["rounds"]:
        for m in rd["matches"]:
            if "t3" in (m["home"], m["away"]):
                if rd["round"] > 2:
                    assert m["status"] == "forfeit"
                    assert m["awarded_to"] == (m["away"] if m["home"] == "t3" else m["home"])
                else:
                    assert m["status"] == "scheduled"
    s = r["summary"]
    assert s["total"] == 10 and s["forfeit"] + s["scheduled"] == 10 and s["voided"] == 0
    v = generate({"format": "round_robin", "teams": teams(4),
                  "params": {"withdrawals": [{"team_id": "t1", "after_round": 1}, {"team_id": "t2", "after_round": 0}],
                             "withdrawal_policy": "void_all"}})
    assert v["summary"]["voided"] == 5


@pytest.mark.parametrize("body", [
    {"format": "round_robin", "teams": ["t1"]},
    {"format": "round_robin", "teams": ["t1", "t1"]},
    {"format": "round_robin", "teams": teams(4), "params": {"legs": 3}},
    {"format": "round_robin", "teams": teams(4), "params": {"withdrawal_policy": "x"}},
    {"format": "round_robin", "teams": teams(4), "params": {"withdrawals": [{"team_id": "zz", "after_round": 1}]}},
    {"format": "round_robin", "teams": teams(4), "params": {"withdrawals": [{"team_id": "t1", "after_round": 9}]}},
    {"format": "nope", "teams": teams(4)},
    {"format": "double_elim", "teams": teams(2)},
    {"format": "double_elim", "teams": teams(4), "params": {"bracket_reset": "yes"}},
    {"format": "swiss", "teams": teams(4), "params": {"round": 2, "history": []}},
    {"format": "swiss", "teams": teams(4), "params": {"total_rounds": 4}},
    {"format": "swiss", "teams": teams(4), "params": {"round": 2, "total_rounds": 3, "history": [
        {"round": 1, "bye": None, "matches": [{"home": "t1", "away": "zz", "result": "home"}]}]}},
    {"format": "single_elim", "teams": teams(4), "params": {"results": [{"match_id": "R9M9", "winner": "t1"}]}},
    {"format": "single_elim", "teams": teams(4), "params": {"results": [{"match_id": "R1M1", "winner": "t2"}]}},
    {"format": "single_elim", "teams": teams(4), "params": {"third_place_match": 1}},
])
def test_fixture_validation(body):
    with pytest.raises(ApiError) as e:
        generate(body)
    assert e.value.status == 400 and e.value.code == "VALIDATION_ERROR"


def test_swiss_round_one_exact():
    r = generate({"format": "swiss", "teams": teams(5), "params": {"total_rounds": 3}})
    assert [(p["home"], p["away"]) for p in r["pairings"]] == [("t1", "t3"), ("t2", "t4")]
    assert r["bye"] == "t5"


def test_swiss_spec_example():
    r = generate({"format": "swiss", "teams": teams(5), "params": {"total_rounds": 3, "round": 2, "history": [
        {"round": 1, "bye": "t5", "matches": [{"home": "t1", "away": "t3", "result": "home"},
                                              {"home": "t2", "away": "t4", "result": "draw"}]}]}})
    assert r["bye"] == "t3"
    assert r["standings"][0] == {"rank": 1, "team_id": "t1", "score": 1.0, "buchholz": 0.0}
    assert r["standings"][2] == {"rank": 3, "team_id": "t2", "score": 0.5, "buchholz": 0.5}
    pairs = {frozenset((p["home"], p["away"])) for p in r["pairings"]}
    assert frozenset(("t2", "t4")) not in pairs and len(pairs) == 2


def test_swiss_no_valid_pairing():
    hist = [{"round": 1, "bye": None, "matches": [{"home": "t1", "away": "t2", "result": "home"},
                                                   {"home": "t1", "away": "t3", "result": "home"},
                                                   {"home": "t1", "away": "t4", "result": "home"}]}]
    with pytest.raises(ApiError) as e:
        generate({"format": "swiss", "teams": teams(4), "params": {"total_rounds": 3, "round": 2, "history": hist}})
    assert e.value.status == 409 and e.value.code == "NO_VALID_PAIRING" and e.value.details == {"round": 2}


def test_swiss_matching_is_optimal_bruteforce():
    def brute(players, score, played):
        best = None

        def rec(rem, c):
            nonlocal best
            if not rem:
                best = c if best is None or c < best else best
                return
            a = rem[0]
            for b in rem[1:]:
                if frozenset((a, b)) not in played:
                    rec([x for x in rem if x not in (a, b)], c + abs(score[a] - score[b]))

        rec(players, 0)
        return best

    rnd = random.Random(7)
    for _ in range(200):
        n = rnd.choice([2, 4, 6, 8])
        ps = [f"p{i}" for i in range(n)]
        sc = {p: rnd.randint(0, 6) for p in ps}
        played = {frozenset(rnd.sample(ps, 2)) for _ in range(rnd.randint(0, 2 * n))}
        cost, _ = min_cost_pairing(ps, sc, played)
        assert cost == brute(ps, sc, played)


def test_swiss_large_field_is_fast():
    n = 64
    hist = []
    for rnd in range(1, 6):
        r = generate({"format": "swiss", "teams": teams(n), "params": {"total_rounds": 6, "round": rnd, "history": hist}})
        hist.append({"round": rnd, "bye": r["bye"],
                     "matches": [{"home": p["home"], "away": p["away"], "result": "home"} for p in r["pairings"]]})
    assert len(hist) == 5


def test_seed_order():
    assert seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]


def test_single_elim_byes_and_results():
    r = generate({"format": "single_elim", "teams": teams(6),
                  "params": {"third_place_match": True, "results": [{"match_id": "R1M2", "winner": "t4"}]}})
    assert r["bracket_size"] == 8 and len(r["rounds"]) == 3
    r1 = {m["match_id"]: m for m in r["rounds"][0]["matches"]}
    assert r1["R1M1"]["bye"] and r1["R1M1"]["away"] is None and r1["R1M1"]["winner"] == "t1"
    assert r1["R1M2"]["home"] == "t4" and r1["R1M2"]["away"] == "t5" and r1["R1M2"]["winner"] == "t4"
    r2 = {m["match_id"]: m for m in r["rounds"][1]["matches"]}
    assert r2["R2M1"]["home"] == "t1" and r2["R2M1"]["away"] == "t4"
    assert r2["R2M1"]["loser_to"] == {"match_id": "TP", "slot": "home"}
    final = [m for m in r["rounds"][2]["matches"] if m["match_id"] == "R3M1"][0]
    assert final["winner_to"] is None


@pytest.mark.parametrize("n", [3, 4, 5, 7, 8, 12, 16, 33])
def test_double_elim_structure_and_playthrough(n):
    results = []
    for _ in range(500):
        r = generate({"format": "double_elim", "teams": teams(n), "params": {"bracket_reset": True, "results": results}})
        allm = [m for k in ("winners", "losers") for x in r[k] for m in x["matches"]] + r["grand_final"]
        nxt = [m for m in allm if m["winner"] is None and m["home"] and m["away"] and m["match_id"] != "GF2"]
        if not nxt:
            break
        m = nxt[0]
        results.append({"match_id": m["match_id"], "winner": m["away"] if m["match_id"] == "GF1" else m["home"]})
    size = r["bracket_size"]
    assert sum(len(x["matches"]) for x in r["losers"]) == size - 2
    feeds = Counter()
    for m in allm:
        for key in ("winner_to", "loser_to"):
            if m[key]:
                feeds[(m[key]["match_id"], m[key]["slot"])] += 1
        if m["bracket"] == "winners":
            assert m["loser_to"] is not None
        if m["bracket"] == "losers":
            assert m["loser_to"] is None
    for m in allm:
        if not m["match_id"].startswith("WR1M"):
            assert feeds[(m["match_id"], "home")] == 1 and feeds[(m["match_id"], "away")] == 1
    gf1, gf2 = r["grand_final"]
    assert gf1["winner"] == gf1["away"] and gf2["conditional"] is True and gf2["required"] is True


def test_double_elim_wb_champion_ends_event():
    r = generate({"format": "double_elim", "teams": teams(4), "params": {"bracket_reset": True}})
    assert r["grand_final"][1]["required"] is None
    r = generate({"format": "double_elim", "teams": teams(4), "params": {"bracket_reset": False}})
    assert len(r["grand_final"]) == 1
