"""League registration and standings (POST /audit/v1/leagues, GET /audit/v1/standings/{id})."""
from .. import db, seed
from ..db import J
from ..domain import scoring
from ..domain.sports import validate_tie_break_order
from ..domain.standings import Table, result_from_projection
from ..domain.validate import id_list, is_id, is_int
from ..errors import ApiError, conflict, not_found, validation
from .matches import get_sport, load_logs


def _validate(body: dict) -> dict:
    bad = []
    if not is_id(body.get("league_id")):
        bad.append("league_id")
    if not is_id(body.get("sport_id")):
        bad.append("sport_id")
    try:
        teams = id_list(body.get("teams"), "teams", 2, 40)
    except ApiError:
        bad.append("teams")
        teams = []
    fixtures = body.get("fixtures")
    if not isinstance(fixtures, list):
        bad.append("fixtures")
        fixtures = []
    seen = set()
    for f in fixtures:
        if (not isinstance(f, dict) or not is_id(f.get("match_id")) or f.get("home") not in teams
                or f.get("away") not in teams or f.get("home") == f.get("away") or f["match_id"] in seen):
            bad.append("fixtures")
            break
        seen.add(f["match_id"])
    points = body.get("points") or {}
    if not isinstance(points, dict) or any(k in points and not is_int(points[k]) for k in ("win", "draw", "loss")):
        bad.append("points")
        points = {}
    try:
        tbo = validate_tie_break_order(body.get("tie_break_order")) if body.get("tie_break_order") is not None else None
    except ApiError:
        bad.append("tie_break_order")
        tbo = None
    q = body.get("qualification")
    spots = q.get("spots") if isinstance(q, dict) else None
    if not is_int(spots) or not (1 <= spots <= max(len(teams), 1)):
        bad.append("qualification")
    lots = body.get("lots_seed")
    if lots is not None and not is_int(lots):
        bad.append("lots_seed")
    if bad:
        raise validation(bad)
    return {
        "league_id": body["league_id"], "sport_id": body["sport_id"], "teams": teams,
        "fixtures": [{"match_id": f["match_id"], "home": f["home"], "away": f["away"]} for f in fixtures],
        "points": {"win": points.get("win", 3), "draw": points.get("draw", 1), "loss": points.get("loss", 0)},
        "tie_break_order": tbo, "spots": spots, "lots_seed": lots,
    }


def register(body: dict) -> dict:
    cfg = _validate(body)
    with db.tx() as cur:
        db.lock(cur, "leagues")
        sport = get_sport(cur, cfg["sport_id"])
        if sport is None:
            raise not_found("SPORT_NOT_FOUND", f"Sport {cfg['sport_id']} not found.", sport_id=cfg["sport_id"])
        cur.execute("SELECT 1 FROM leagues WHERE league_id = %s", (cfg["league_id"],))
        if cur.fetchone():
            raise conflict("LEAGUE_EXISTS", f"League {cfg['league_id']} already exists.", league_id=cfg["league_id"])
        ids = [f["match_id"] for f in cfg["fixtures"]]
        cur.execute("SELECT match_id FROM matches WHERE match_id = ANY(%s)", (ids,))
        taken = [r["match_id"] for r in cur.fetchall()]
        if taken:
            raise conflict("MATCH_EXISTS", f"Match {taken[0]} already exists.", match_id=taken[0])
        if cfg["tie_break_order"] is None:
            cfg["tie_break_order"] = sport.get("tie_break_order") or validate_tie_break_order(None)
        if cfg["lots_seed"] is None:
            cfg["lots_seed"] = seed.current_seed(cur)
        cur.execute("INSERT INTO leagues (league_id, tenant_id, sport_id, name, config) VALUES (%s, NULL, %s, %s, %s)",
                    (cfg["league_id"], cfg["sport_id"], cfg["league_id"], J(cfg)))
        for f in cfg["fixtures"]:
            cur.execute("INSERT INTO matches (match_id, sport_id, league_id, home_team_id, away_team_id)"
                        " VALUES (%s,%s,%s,%s,%s)", (f["match_id"], cfg["sport_id"], cfg["league_id"], f["home"], f["away"]))
    return {"league_id": cfg["league_id"], "status": "created", "team_count": len(cfg["teams"]),
            "fixture_count": len(cfg["fixtures"])}


def standings(league_id: str) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT * FROM leagues WHERE league_id = %s", (league_id,))
        league = cur.fetchone()
        if league is None:
            raise not_found("LEAGUE_NOT_FOUND", f"League {league_id} not found.", league_id=league_id)
        cfg = league["config"]
        sport = get_sport(cur, league["sport_id"])
        if not cfg.get("teams"):
            cfg = _derived_config(cur, league, sport)
        logs = load_logs(cur, [f["match_id"] for f in cfg["fixtures"]])
    results = []
    for f in cfg["fixtures"]:
        log = logs.get(f["match_id"])
        results.append(result_from_projection(f, scoring.project(log) if log else None))
    out = Table(cfg, sport, results).compute()
    return {"league_id": league_id, "sport_id": league["sport_id"], "qualification_spots": cfg["spots"],
            "table": out["table"], "h2h": out["h2h"]}


def _derived_config(cur, league: dict, sport: dict) -> dict:
    """Seeded tenant leagues: teams are the league's clubs, fixtures are its matches."""
    cur.execute("SELECT club_id FROM clubs WHERE league_id = %s ORDER BY club_id", (league["league_id"],))
    teams = [r["club_id"] for r in cur.fetchall()]
    cur.execute("SELECT match_id, home_team_id, away_team_id FROM matches WHERE league_id = %s ORDER BY ord",
                (league["league_id"],))
    fixtures = [{"match_id": r["match_id"], "home": r["home_team_id"], "away": r["away_team_id"]}
                for r in cur.fetchall()]
    return {"league_id": league["league_id"], "teams": teams, "fixtures": fixtures,
            "points": {"win": 3, "draw": 1, "loss": 0},
            "tie_break_order": sport.get("tie_break_order") or validate_tie_break_order(None),
            "spots": max(1, min(2, len(teams))), "lots_seed": seed.current_seed(cur)}
