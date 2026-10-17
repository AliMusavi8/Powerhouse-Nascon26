"""Event-sourced scoring (spec 5.9). Pure functions over a match's append-only event log.

Everything sport-specific comes from the sport config: event names, points/runs/rounds, ball and
wicket limits, best-of, draw policy.
"""
from ..errors import ApiError, conflict, not_found, validation
from .validate import is_id, is_int

EVENT_TYPES = ("match_init", "match_start", "score", "discipline", "tiebreak_winner", "match_end", "compensation")
COMPENSABLE = ("score", "discipline", "tiebreak_winner")


def validate_envelope(body: dict) -> None:
    bad = []
    if not is_id(body.get("event_id")):
        bad.append("event_id")
    if not is_id(body.get("match_id")):
        bad.append("match_id")
    if body.get("type") not in EVENT_TYPES:
        bad.append("type")
    if not isinstance(body.get("payload"), dict):
        bad.append("payload")
    if bad:
        raise validation(bad)


def validate_init_payload(payload: dict) -> None:
    bad = [f for f in ("sport_id", "home_team_id", "away_team_id") if not is_id(payload.get(f))]
    if payload.get("league_id") is not None and not is_id(payload.get("league_id")):
        bad.append("league_id")
    if not bad and payload["home_team_id"] == payload["away_team_id"]:
        bad.append("away_team_id")
    if bad:
        raise validation(bad)


class Log:
    """Derived state of a match log (compensations neutralise their targets)."""

    def __init__(self, match: dict, sport: dict, events: list[dict]):
        self.match, self.sport, self.events = match, sport, events
        self.by_id = {e["event_id"]: e for e in events}
        self.compensated_by: dict[str, str] = {}
        for e in events:
            if e["type"] == "compensation":
                self.compensated_by[e["payload"]["compensates"]] = e["event_id"]
        types = [e["type"] for e in events]
        if "match_end" in types:
            self.status = "completed"
        elif "match_start" in types:
            self.status = "in_progress"
        else:
            self.status = "upcoming"

    def active(self, type_: str):
        return [e for e in self.events if e["type"] == type_ and e["event_id"] not in self.compensated_by]

    def team_ids(self):
        return self.match["home_team_id"], self.match["away_team_id"]

    def tally(self) -> dict:
        model = self.sport["scoring_model"]
        defs = self.sport["scoring_events"]
        out = {t: {"score": 0, "wickets": 0, "balls": 0, "fair_play": 0} for t in self.team_ids()}
        for e in self.active("score"):
            t, d = e["payload"]["team_id"], defs.get(e["payload"]["event_type"], {})
            if model == "event":
                out[t]["score"] += d.get("points", 0)
            elif model == "innings":
                out[t]["score"] += d.get("runs", 0)
                out[t]["balls"] += 1 if d.get("legal_ball") else 0
                out[t]["wickets"] += 1 if d.get("wicket") else 0
            else:
                out[t]["score"] += d.get("rounds", 0)
        for e in self.active("discipline"):
            out[e["payload"]["team_id"]]["fair_play"] += e["payload"]["points"]
        return out

    def tiebreak_team(self):
        tb = self.active("tiebreak_winner")
        return tb[-1]["payload"]["team_id"] if tb else None


def check_event(log: Log, body: dict) -> None:
    """Raise the contract error if `body` may not be appended to `log`."""
    type_, p = body["type"], body["payload"]
    home, away = log.team_ids()
    sport = log.sport
    if type_ == "match_init":
        raise conflict("MATCH_EXISTS", f"Match {body['match_id']} already exists.", match_id=body["match_id"])
    if type_ in ("score", "discipline", "tiebreak_winner"):
        if p.get("team_id") not in (home, away):
            raise validation("team_id", "team_id must be the home or away team.")
    if type_ == "score":
        if not isinstance(p.get("event_type"), str) or p["event_type"] not in sport["scoring_events"]:
            raise ApiError(400, "UNKNOWN_EVENT_TYPE", f"Event type {p.get('event_type')!r} is not defined for this sport.",
                           {"event_type": p.get("event_type")})
    if type_ == "discipline" and not is_int(p.get("points")):
        raise validation("points")
    if type_ == "compensation":
        target_id = p.get("compensates")
        if not is_id(target_id):
            raise validation("compensates")
        if "reason" in p and p["reason"] is not None and not isinstance(p["reason"], str):
            raise validation("reason")

    if type_ == "match_start":
        if log.status != "upcoming":
            raise conflict("ILLEGAL_TRANSITION", f"Cannot start a match that is {log.status}.", status=log.status)
        return
    if type_ in ("score", "discipline", "tiebreak_winner"):
        if log.status != "in_progress":
            raise conflict("MATCH_NOT_IN_PROGRESS", "The match is not in progress.", status=log.status)
        if type_ == "score":
            _check_limits(log, p["team_id"])
        return
    if type_ == "match_end":
        if log.status != "in_progress":
            raise conflict("ILLEGAL_TRANSITION", f"Cannot end a match that is {log.status}.", status=log.status)
        t = log.tally()
        if t[home]["score"] == t[away]["score"] and not sport["draw_allowed"] and log.tiebreak_team() is None:
            raise conflict("TIE_NOT_ALLOWED", "Scores are level and this sport does not allow draws.")
        return
    if type_ == "compensation":
        target = log.by_id.get(p["compensates"])
        if target is None:
            raise not_found("EVENT_NOT_FOUND", f"Event {p['compensates']} not found.", event_id=p["compensates"])
        if target["type"] not in COMPENSABLE or target["event_id"] in log.compensated_by:
            raise conflict("INVALID_COMPENSATION", "This event cannot be compensated.", event_id=target["event_id"])


def _check_limits(log: Log, team_id: str) -> None:
    sport = log.sport
    model, periods = sport["scoring_model"], sport["periods"]
    t = log.tally()
    if model == "innings":
        max_balls = periods["innings_per_team"] * periods["overs_per_innings"] * periods["balls_per_over"]
        max_wkts = periods["innings_per_team"] * periods["wickets_per_innings"]
        if t[team_id]["balls"] >= max_balls or t[team_id]["wickets"] >= max_wkts:
            raise conflict("INNINGS_COMPLETE", "This team's innings is complete.", team_id=team_id)
    elif model == "round":
        need = (periods["best_of"] + 1) // 2
        if any(v["score"] >= need for v in t.values()):
            raise conflict("SERIES_ALREADY_DECIDED", "The series has already been decided.")


def outcome(log: Log) -> tuple[str, str | None]:
    if log.status != "completed":
        return "pending", None
    home, away = log.team_ids()
    t = log.tally()
    hs, as_ = t[home]["score"], t[away]["score"]
    if hs > as_:
        return "home_win", home
    if as_ > hs:
        return "away_win", away
    tb = log.tiebreak_team()
    if tb is not None:
        return ("home_win" if tb == home else "away_win"), tb
    if log.sport["draw_allowed"]:
        return "draw", None
    return "undecided", None


def project(log: Log) -> dict:
    home, away = log.team_ids()
    t = log.tally()
    innings = log.sport["scoring_model"] == "innings"
    bpo = log.sport["periods"].get("balls_per_over", 6) if innings else None

    def side(team):
        v = t[team]
        return {"team_id": team, "score": v["score"],
                "wickets": v["wickets"] if innings else None,
                "balls": v["balls"] if innings else None,
                "overs": f"{v['balls'] // bpo}.{v['balls'] % bpo}" if innings else None,
                "fair_play": v["fair_play"]}

    result, winner = outcome(log)
    return {
        "match_id": log.match["match_id"], "sport_id": log.match["sport_id"], "league_id": log.match.get("league_id"),
        "status": log.status, "outcome": result, "winner_team_id": winner,
        "tiebreak_winner_team_id": log.tiebreak_team(),
        "home": side(home), "away": side(away),
        "version": len(log.events),
        "events": [{"sequence": e["sequence"], "event_id": e["event_id"], "type": e["type"], "payload": e["payload"],
                    "signature": e["signature"], "compensated": e["event_id"] in log.compensated_by,
                    "compensated_by": log.compensated_by.get(e["event_id"])} for e in log.events],
    }
