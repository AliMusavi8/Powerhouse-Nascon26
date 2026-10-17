"""Roster rules (spec 5.11). Pure functions over an in-memory snapshot of one league's roster."""
from datetime import date, timedelta

from ..errors import ApiError, conflict, not_found, validation
from .validate import is_id, is_int, parse_date

ROLES = ("captain", "vice_captain", "starter", "substitute")
TYPES = ("transfer", "loan", "release")


# ---------------------------------------------------------------------------- setup

def validate_setup(body: dict) -> dict:
    bad = []
    lg = body.get("league")
    if not isinstance(lg, dict):
        raise validation("league")
    for f in ("league_id", "tenant_id", "sport_id"):
        if not is_id(lg.get(f)):
            bad.append(f"league.{f}")
    win = lg.get("transfer_window")
    if (not isinstance(win, dict) or parse_date(win.get("open")) is None or parse_date(win.get("close")) is None
            or parse_date(win["open"]) > parse_date(win["close"])):
        bad.append("league.transfer_window")
    if lg.get("max_squad_size") is not None and (not is_int(lg["max_squad_size"]) or lg["max_squad_size"] < 1):
        bad.append("league.max_squad_size")
    rp = lg.get("required_positions")
    if rp is not None and (not isinstance(rp, dict) or any(not is_int(v) or v < 0 for v in rp.values())):
        bad.append("league.required_positions")

    squads = body.get("squads")
    squad_ids = set()
    if not isinstance(squads, list):
        bad.append("squads")
        squads = []
    for s in squads:
        if not isinstance(s, dict) or not is_id(s.get("squad_id")) or s["squad_id"] in squad_ids \
                or not is_id(s.get("tenant_id")) or (s.get("club_id") is not None and not is_id(s.get("club_id"))):
            bad.append("squads")
            break
        squad_ids.add(s["squad_id"])

    players = body.get("players")
    player_ids = set()
    if not isinstance(players, list):
        bad.append("players")
        players = []
    for p in players:
        if (not isinstance(p, dict) or not is_id(p.get("player_id")) or p["player_id"] in player_ids
                or not isinstance(p.get("position"), str) or p.get("squad_id") not in squad_ids
                or p.get("role", "substitute") not in ROLES):
            bad.append("players")
            break
        player_ids.add(p["player_id"])

    live = body.get("matches_in_progress") or []
    if not isinstance(live, list) or any(not isinstance(m, dict) or not is_id(m.get("match_id")) for m in live):
        bad.append("matches_in_progress")
    if bad:
        raise validation(bad)
    return {"league": lg, "squads": squads, "players": players, "live": live}


# ---------------------------------------------------------------------------- transfers

def validate_transfer(body: dict) -> dict:
    bad = []
    for f in ("request_id", "league_id", "player_id", "from_squad_id"):
        if not is_id(body.get(f)):
            bad.append(f)
    t = body.get("type")
    if t not in TYPES:
        bad.append("type")
    if t != "release" and not is_id(body.get("to_squad_id")):
        bad.append("to_squad_id")
    eff = parse_date(body.get("effective_date"))
    if eff is None:
        bad.append("effective_date")
    end = None
    if t == "loan":
        end = parse_date(body.get("loan_end_date"))
        if end is None or (eff is not None and end <= eff):
            bad.append("loan_end_date")
    for f in ("reason", "requested_by"):
        if body.get(f) is not None and not isinstance(body.get(f), str):
            bad.append(f)
    if bad:
        raise validation(bad)
    return {"eff": eff, "end": end}


def loan_returned(reg: dict, on: date) -> bool:
    return (reg.get("registration_type") == "loan" and reg.get("loan_end_date") is not None
            and on > date.fromisoformat(reg["loan_end_date"]))


def check_transfer(body: dict, eff: date, league: dict, squads: dict, regs: dict, live: list) -> dict:
    """Run checks 2-8 in contract order. Returns the decision used to apply the change."""
    if league is None:
        raise not_found("LEAGUE_NOT_FOUND", f"League {body['league_id']} not found.", league_id=body["league_id"])
    reg = regs.get(body["player_id"])
    if reg is None:
        raise not_found("PLAYER_NOT_FOUND", f"Player {body['player_id']} not found.", player_id=body["player_id"])
    to_id = body.get("to_squad_id") if body["type"] != "release" else None
    for sid in (body["from_squad_id"], to_id):
        if sid is not None and sid not in squads:
            raise not_found("SQUAD_NOT_FOUND", f"Squad {sid} not found.", squad_id=sid)
    cfg = league["config"]
    tenant = cfg["tenant_id"]
    for sid in (body["from_squad_id"], to_id):
        if sid is not None and squads[sid]["tenant_id"] != tenant:
            raise conflict("CROSS_TENANT_TRANSFER", "Squads must belong to the league's tenant.", squad_id=sid)

    returned = loan_returned(reg, eff)
    current = reg["parent_squad_id"] if returned else reg["squad_id"]
    if current != body["from_squad_id"]:
        raise conflict("NOT_IN_SQUAD", "The player is not registered in the from squad.",
                       player_id=body["player_id"], squad_id=current)
    if body["type"] != "release":
        win = cfg["transfer_window"]
        if not (date.fromisoformat(win["open"]) <= eff <= date.fromisoformat(win["close"])):
            raise conflict("TRANSFER_WINDOW_CLOSED", "The transfer window is closed on that date.",
                           effective_date=body["effective_date"])
    if reg.get("registration_type") == "loan" and not returned:
        raise conflict("PLAYER_ON_LOAN", "The player is currently on loan.", player_id=body["player_id"])

    counts: dict[str, int] = {}
    pos_counts: dict[tuple, int] = {}
    for pid, r in regs.items():
        sq = r["parent_squad_id"] if loan_returned(r, eff) else r["squad_id"]
        if sq is None:
            continue
        counts[sq] = counts.get(sq, 0) + 1
        pos_counts[(sq, r["position"])] = pos_counts.get((sq, r["position"]), 0) + 1
    if to_id is not None and counts.get(to_id, 0) + 1 > cfg["max_squad_size"]:
        raise conflict("SQUAD_FULL", f"Squad {to_id} is full.", squad_id=to_id, max_squad_size=cfg["max_squad_size"])
    need = cfg["required_positions"].get(reg["position"], 0)
    if pos_counts.get((body["from_squad_id"], reg["position"]), 0) - 1 < need:
        raise conflict("MIN_POSITION_VIOLATION",
                       f"Squad {body['from_squad_id']} would have fewer than {need} {reg['position']} players.",
                       squad_id=body["from_squad_id"], position=reg["position"], required=need)

    blocking = None
    for m in live:
        if body["from_squad_id"] in (m.get("home_squad_id"), m.get("away_squad_id")):
            blocking = m["match_id"]
            break
    return {"reg": reg, "returned": returned, "to": to_id, "blocking": blocking}


def next_day(d: str) -> str:
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


def squad_on(reg: dict, on: date) -> tuple[str | None, str | None]:
    """(current_squad_id, parent_squad_id) for a registration on a given date."""
    if reg.get("registration_type") == "loan":
        start = date.fromisoformat(reg["start_date"])
        end = date.fromisoformat(reg["loan_end_date"])
        if on < start or on > end:
            return reg["parent_squad_id"], None
        return reg["squad_id"], reg["parent_squad_id"]
    return reg["squad_id"], None


__all__ = ["ApiError"]
