SETUP = {
    "league": {"league_id": "lg-r1", "tenant_id": "tenant-alpha", "sport_id": "football",
               "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
               "max_squad_size": 3, "required_positions": {"gk": 1}},
    "squads": [{"squad_id": "sq-a", "club_id": "club-a", "tenant_id": "tenant-alpha", "name": "A"},
               {"squad_id": "sq-b", "club_id": "club-b", "tenant_id": "tenant-alpha", "name": "B"},
               {"squad_id": "sq-x", "club_id": "club-x", "tenant_id": "tenant-beta", "name": "X"}],
    "players": [{"player_id": "p1", "name": "Ali", "position": "gk", "squad_id": "sq-a", "role": "captain"},
                {"player_id": "p2", "name": "Bilal", "position": "df", "squad_id": "sq-a", "role": "starter"},
                {"player_id": "p3", "name": "Cheema", "position": "df", "squad_id": "sq-b", "role": "starter"}],
    "matches_in_progress": [],
}


def tr(rid, player, type_, frm, to, eff="2026-09-15", end=None):
    return {"request_id": rid, "league_id": "lg-r1", "player_id": player, "type": type_, "from_squad_id": frm,
            "to_squad_id": to, "effective_date": eff, "loan_end_date": end, "reason": "Tactical move",
            "requested_by": "user-77"}


def code(r):
    return r.json()["error"]["code"]


def test_roster_rules_in_order(fresh):
    api = fresh
    r = api.post("/audit/v1/roster/setup", SETUP)
    assert r.status_code == 201 and r.json()["squad_counts"] == {"sq-a": 2, "sq-b": 1, "sq-x": 0}
    T = "/audit/v1/roster/transfer"
    assert api.post(T, tr("x1", "p2", "loan", "sq-a", "sq-b")).status_code == 400  # loan without end date
    assert api.post(T, tr("x1", "p2", "transfer", "sq-a", None)).status_code == 400
    assert code(api.post(T, dict(tr("x1", "p2", "transfer", "sq-a", "sq-b"), league_id="nope"))) == "LEAGUE_NOT_FOUND"
    assert code(api.post(T, tr("x1", "p9", "transfer", "sq-a", "sq-b"))) == "PLAYER_NOT_FOUND"
    assert code(api.post(T, tr("x1", "p2", "transfer", "sq-a", "sq-z"))) == "SQUAD_NOT_FOUND"
    assert code(api.post(T, tr("x1", "p2", "transfer", "sq-a", "sq-x"))) == "CROSS_TENANT_TRANSFER"
    assert code(api.post(T, tr("x1", "p2", "transfer", "sq-b", "sq-a"))) == "NOT_IN_SQUAD"
    assert code(api.post(T, tr("x1", "p2", "transfer", "sq-a", "sq-b", eff="2026-10-01"))) == "TRANSFER_WINDOW_CLOSED"
    assert code(api.post(T, tr("x1", "p1", "transfer", "sq-a", "sq-b"))) == "MIN_POSITION_VIOLATION"

    r = api.post(T, tr("tr-1", "p2", "transfer", "sq-a", "sq-b", eff="2026-09-30"))
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["state"] == "active" and j["registration"]["role"] == "substitute"
    assert j["audit_entry"]["audit_id"] == "au-0001" and j["audit_entry"]["who"] == "user-77"
    assert api.post(T, tr("tr-1", "p2", "transfer", "sq-a", "sq-b", eff="2026-09-30")).status_code == 200
    # sq-b now has p3 + p2 = 2; one more fits, then full.
    api.post("/audit/v1/roster/setup", dict(SETUP, players=SETUP["players"] + [
        {"player_id": "p4", "name": "D", "position": "fw", "squad_id": "sq-b", "role": "starter"},
        {"player_id": "p5", "name": "E", "position": "fw", "squad_id": "sq-b", "role": "starter"}]))
    assert code(api.post(T, tr("x2", "p2", "transfer", "sq-a", "sq-b"))) == "SQUAD_FULL"
    r = api.post(T, tr("rel-1", "p2", "release", "sq-a", None, eff="2026-12-25"))
    assert r.status_code == 201 and r.json()["registration"] is None
    h = api.get("/audit/v1/roster/history/p2").json()
    assert h["current_squad_id"] is None and [e["action"] for e in h["history"]] == ["release"]


def test_loan_auto_return_once(fresh):
    api = fresh
    api.post("/audit/v1/roster/setup", SETUP)
    T = "/audit/v1/roster/transfer"
    r = api.post(T, tr("ln-1", "p2", "loan", "sq-a", "sq-b", eff="2026-09-10", end="2026-12-31"))
    assert r.status_code == 201 and r.json()["registration"]["parent_squad_id"] == "sq-a"
    assert code(api.post(T, tr("x", "p2", "transfer", "sq-b", "sq-a"))) == "PLAYER_ON_LOAN"
    h = api.get("/audit/v1/roster/history/p2?as_of=2026-11-01").json()
    assert h["current_squad_id"] == "sq-b" and h["parent_squad_id"] == "sq-a" and len(h["history"]) == 1
    for _ in range(2):
        h = api.get("/audit/v1/roster/history/p2?as_of=2027-01-05").json()
        assert h["current_squad_id"] == "sq-a" and h["parent_squad_id"] is None
        assert [e["action"] for e in h["history"]] == ["loan", "loan_return"]
        assert h["history"][1]["who"] == "system"
    assert api.get("/audit/v1/roster/history/p2?as_of=bad").status_code == 400
    assert code(api.get("/audit/v1/roster/history/ghost")) == "PLAYER_NOT_FOUND"


def test_deferred_until_match_end(fresh):
    api = fresh
    api.post("/audit/v1/roster/setup", dict(SETUP, matches_in_progress=[
        {"match_id": "m-live", "home_squad_id": "sq-a", "away_squad_id": "sq-b"}]))
    r = api.post("/audit/v1/roster/transfer", tr("tr-9", "p2", "transfer", "sq-a", "sq-b", eff="2026-09-30"))
    assert r.status_code == 201
    assert r.json()["state"] == "deferred_until_match_end" and r.json()["blocking_match_id"] == "m-live"
