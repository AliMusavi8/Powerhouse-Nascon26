"""Sport configuration validation (spec 5.6). A sport is pure data; no sport is special-cased in code."""
import re

from ..errors import validation
from .validate import is_int

SPORT_ID_RE = re.compile(r"^[a-z0-9_-]{2,40}$")
EVENT_KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")
MODELS = ("event", "innings", "round")
OVERTIME_POLICIES = ("none", "extra_time", "shootout", "golden_score", "super_over")
TIE_BREAKS = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]


def _int_at_least(v, lo: int) -> bool:
    return is_int(v) and v >= lo


def validate_tie_break_order(value, field: str = "tie_break_order") -> list[str]:
    if value is None:
        return list(TIE_BREAKS)
    if (not isinstance(value, list) or any(t not in TIE_BREAKS for t in value)
            or len(set(value)) != len(value)):
        raise validation(field)
    return list(value)


def validate_sport(body: dict) -> dict:
    bad: list[str] = []
    sport_id = body.get("sport_id")
    if not isinstance(sport_id, str) or not SPORT_ID_RE.match(sport_id):
        bad.append("sport_id")
    name = body.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= 80):
        bad.append("name")
    model = body.get("scoring_model")
    if model not in MODELS:
        bad.append("scoring_model")

    periods = body.get("periods")
    if not isinstance(periods, dict):
        bad.append("periods")
    elif model == "event":
        if not _int_at_least(periods.get("count"), 1) or not _int_at_least(periods.get("duration_minutes"), 1):
            bad.append("periods")
    elif model == "innings":
        keys = ("innings_per_team", "overs_per_innings", "balls_per_over", "wickets_per_innings")
        if not all(_int_at_least(periods.get(k), 1) for k in keys):
            bad.append("periods")
    elif model == "round":
        best_of = periods.get("best_of")
        if not _int_at_least(best_of, 1) or best_of % 2 == 0:
            bad.append("periods")

    events = body.get("scoring_events")
    if not isinstance(events, dict) or not events:
        bad.append("scoring_events")
    else:
        for key, val in events.items():
            if not EVENT_KEY_RE.match(key) or not isinstance(val, dict) or not _event_value_ok(model, val):
                bad.append("scoring_events")
                break

    if not isinstance(body.get("draw_allowed"), bool):
        bad.append("draw_allowed")

    overtime = body.get("overtime")
    if (not isinstance(overtime, dict) or overtime.get("policy") not in OVERTIME_POLICIES
            or ("duration_minutes" in overtime and overtime["duration_minutes"] is not None
                and not _int_at_least(overtime["duration_minutes"], 0))):
        bad.append("overtime")

    tbo = body.get("tie_break_order")
    try:
        tbo = validate_tie_break_order(tbo)
    except Exception:
        bad.append("tie_break_order")

    roster = body.get("roster")
    if not isinstance(roster, dict):
        bad.append("roster")
    else:
        lo, hi, req = roster.get("min_squad_size"), roster.get("max_squad_size"), roster.get("required_positions")
        if (not _int_at_least(lo, 1) or not _int_at_least(hi, 1) or lo > hi or not isinstance(req, dict)
                or any(not isinstance(k, str) or not k or not _int_at_least(v, 0) for k, v in req.items())):
            bad.append("roster")

    if bad:
        raise validation(bad, "Invalid sport configuration.")
    config = {k: body[k] for k in ("sport_id", "name", "scoring_model", "periods", "scoring_events",
                                   "draw_allowed", "overtime", "roster")}
    config["tie_break_order"] = tbo
    return config


def _event_value_ok(model, val: dict) -> bool:
    if model == "event":
        return _int_at_least(val.get("points"), 1)
    if model == "innings":
        return (_int_at_least(val.get("runs"), 0) and isinstance(val.get("legal_ball"), bool)
                and isinstance(val.get("wicket"), bool))
    if model == "round":
        return _int_at_least(val.get("rounds"), 1)
    return False
