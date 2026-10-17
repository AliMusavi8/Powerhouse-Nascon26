from datetime import date

import pytest

from app.domain import roster as rules
from app.errors import ApiError

LEAGUE = {"config": {"tenant_id": "ta", "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
                     "max_squad_size": 2, "required_positions": {"gk": 1}}}
SQUADS = {"a": {"tenant_id": "ta"}, "b": {"tenant_id": "ta"}, "x": {"tenant_id": "tb"}}


def regs():
    return {
        "p1": {"player_id": "p1", "position": "gk", "squad_id": "a", "parent_squad_id": None,
               "registration_type": "initial", "loan_end_date": None, "start_date": None},
        "p2": {"player_id": "p2", "position": "df", "squad_id": "a", "parent_squad_id": None,
               "registration_type": "initial", "loan_end_date": None, "start_date": None},
        "p3": {"player_id": "p3", "position": "df", "squad_id": "b", "parent_squad_id": None,
               "registration_type": "loan", "loan_end_date": "2026-09-20", "start_date": "2026-09-01"},
    }


def body(player="p2", type_="transfer", frm="a", to="b", eff="2026-09-15", end=None):
    return {"request_id": "r", "league_id": "l", "player_id": player, "type": type_, "from_squad_id": frm,
            "to_squad_id": to, "effective_date": eff, "loan_end_date": end}


def check(b, league=LEAGUE, live=(), r=None):
    parsed = rules.validate_transfer(b)
    return rules.check_transfer(b, parsed["eff"], league, SQUADS, r or regs(), list(live))


def code(b, **kw):
    with pytest.raises(ApiError) as e:
        check(b, **kw)
    return e.value.code


def test_validation():
    for b in (body(type_="swap"), body(to=None), body(eff="2026-13-01"), body(type_="loan", end="2026-09-01"),
              dict(body(), reason=5)):
        with pytest.raises(ApiError) as e:
            rules.validate_transfer(b)
        assert e.value.code == "VALIDATION_ERROR"
    rules.validate_transfer(body(type_="release", to=None))


def test_order_of_checks():
    assert code(body(), league=None) == "LEAGUE_NOT_FOUND"
    assert code(body(player="p9")) == "PLAYER_NOT_FOUND"
    assert code(body(to="zz")) == "SQUAD_NOT_FOUND"
    assert code(body(to="x")) == "CROSS_TENANT_TRANSFER"
    assert code(body(frm="b")) == "NOT_IN_SQUAD"
    assert code(body(eff="2026-08-31")) == "TRANSFER_WINDOW_CLOSED"
    assert code(body(player="p3", frm="b", to="a", eff="2026-09-10")) == "PLAYER_ON_LOAN"
    assert code(body(player="p1")) == "MIN_POSITION_VIOLATION"
    r = regs()
    r["p4"] = dict(r["p2"], player_id="p4", squad_id="b")
    assert code(body(), r=r) == "SQUAD_FULL"


def test_loan_return_and_deferred():
    # After the loan end date p3 is back with its parent squad.
    r = regs()
    r["p3"]["parent_squad_id"] = "a"
    d = check(body(player="p3", frm="a", to="b", eff="2026-09-25", type_="release"), r=r)
    assert d["returned"] is True
    d = check(body(), live=[{"match_id": "m", "home_squad_id": "a", "away_squad_id": "b"}])
    assert d["blocking"] == "m"
    assert check(body(type_="release", to=None, eff="2027-01-01"))["to"] is None


def test_squad_on_dates():
    reg = {"registration_type": "loan", "start_date": "2026-09-10", "loan_end_date": "2026-09-20",
           "squad_id": "b", "parent_squad_id": "a"}
    assert rules.squad_on(reg, date(2026, 9, 15)) == ("b", "a")
    assert rules.squad_on(reg, date(2026, 9, 21)) == ("a", None)
    assert rules.next_day("2026-12-31") == "2027-01-01"


def test_setup_validation():
    good = {"league": {"league_id": "l", "tenant_id": "t", "sport_id": "football",
                       "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"}},
            "squads": [{"squad_id": "a", "tenant_id": "t"}],
            "players": [{"player_id": "p", "position": "gk", "squad_id": "a"}]}
    assert rules.validate_setup(good)["league"]["league_id"] == "l"
    for bad in ({**good, "league": {**good["league"], "transfer_window": {"open": "2026-10-01", "close": "2026-09-01"}}},
                {**good, "players": [{"player_id": "p", "position": "gk", "squad_id": "zz"}]},
                {**good, "squads": "x"}, {**good, "league": None}):
        with pytest.raises(ApiError):
            rules.validate_setup(bad)
