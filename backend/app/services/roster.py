"""Roster scenarios, transfers/loans/releases and the immutable audit trail."""
from datetime import date

from .. import crypto, db
from ..db import J
from ..domain import roster as rules
from ..domain.validate import is_id, parse_date, utc_now_iso
from ..errors import not_found, validation
from .matches import get_sport

ROSTER_LOCK = "roster"


def setup(body: dict) -> dict:
    data = rules.validate_setup(body)
    lg = data["league"]
    with db.tx() as cur:
        db.lock(cur, ROSTER_LOCK)
        sport = get_sport(cur, lg["sport_id"])
        if sport is None and (lg.get("max_squad_size") is None or lg.get("required_positions") is None):
            raise not_found("SPORT_NOT_FOUND", f"Sport {lg['sport_id']} not found.", sport_id=lg["sport_id"])
        roster_cfg = (sport or {}).get("roster", {})
        cfg = {
            "league_id": lg["league_id"], "tenant_id": lg["tenant_id"], "sport_id": lg["sport_id"],
            "transfer_window": {"open": lg["transfer_window"]["open"], "close": lg["transfer_window"]["close"]},
            "max_squad_size": lg["max_squad_size"] if lg.get("max_squad_size") is not None
            else roster_cfg.get("max_squad_size"),
            "required_positions": lg["required_positions"] if lg.get("required_positions") is not None
            else roster_cfg.get("required_positions", {}),
        }
        league_id = lg["league_id"]
        for table in ("squads", "registrations", "roster_live_matches", "roster_audit", "roster_requests"):
            cur.execute(f"DELETE FROM {table} WHERE league_id = %s", (league_id,))
        cur.execute("INSERT INTO roster_leagues (league_id, config) VALUES (%s, %s) "
                    "ON CONFLICT (league_id) DO UPDATE SET config = EXCLUDED.config", (league_id, J(cfg)))
        for s in data["squads"]:
            cur.execute("INSERT INTO squads (league_id, squad_id, club_id, tenant_id, name) VALUES (%s,%s,%s,%s,%s)",
                        (league_id, s["squad_id"], s.get("club_id"), s["tenant_id"], s.get("name")))
        counts = {s["squad_id"]: 0 for s in data["squads"]}
        for p in data["players"]:
            counts[p["squad_id"]] += 1
            cur.execute("INSERT INTO registrations (league_id, player_id, name, position, squad_id, parent_squad_id,"
                        " role, registration_type, start_date, loan_end_date)"
                        " VALUES (%s,%s,%s,%s,%s,NULL,%s,'initial',NULL,NULL)",
                        (league_id, p["player_id"], p.get("name"), p["position"], p["squad_id"],
                         p.get("role", "substitute")))
        for m in data["live"]:
            cur.execute("INSERT INTO roster_live_matches (league_id, match_id, home_squad_id, away_squad_id)"
                        " VALUES (%s,%s,%s,%s)", (league_id, m["match_id"], m.get("home_squad_id"), m.get("away_squad_id")))
    return {"league_id": league_id, "status": "configured", "squad_counts": counts}


def _load(cur, league_id: str):
    cur.execute("SELECT * FROM roster_leagues WHERE league_id = %s", (league_id,))
    league = cur.fetchone()
    cur.execute("SELECT * FROM squads WHERE league_id = %s", (league_id,))
    squads = {s["squad_id"]: s for s in cur.fetchall()}
    cur.execute("SELECT * FROM registrations WHERE league_id = %s", (league_id,))
    regs = {r["player_id"]: r for r in cur.fetchall()}
    cur.execute("SELECT * FROM roster_live_matches WHERE league_id = %s", (league_id,))
    live = cur.fetchall()
    return league, squads, regs, live


def _next_audit_id(cur) -> tuple[int, str]:
    cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM roster_audit")
    n = cur.fetchone()["n"]
    return n, f"au-{n:04d}"


def _write_audit(cur, entry: dict, return_key: str | None = None) -> dict:
    seq, audit_id = _next_audit_id(cur)
    entry = {"audit_id": audit_id, **entry}
    cur.execute("INSERT INTO roster_audit (seq, audit_id, league_id, player_id, entry, return_key)"
                " VALUES (%s,%s,%s,%s,%s,%s)",
                (seq, audit_id, entry["league_id"], entry["player_id"], J(entry), return_key))
    return entry


def _materialize_return(cur, reg: dict) -> dict | None:
    """Write the loan_return entry once and move the player back to the lender."""
    key = f"{reg['league_id']}:{reg['player_id']}:{reg['loan_end_date']}"
    cur.execute("SELECT 1 FROM roster_audit WHERE return_key = %s", (key,))
    if cur.fetchone():
        return None
    entry = _write_audit(cur, {
        "action": "loan_return", "player_id": reg["player_id"], "league_id": reg["league_id"],
        "from_squad_id": reg["squad_id"], "to_squad_id": reg["parent_squad_id"],
        "effective_date": rules.next_day(reg["loan_end_date"]), "state": "active",
        "who": "system", "when": utc_now_iso(), "why": "Loan period ended"}, key)
    cur.execute("UPDATE registrations SET squad_id = parent_squad_id, parent_squad_id = NULL, role = 'substitute',"
                " registration_type = 'loan_return', start_date = %s, loan_end_date = NULL"
                " WHERE league_id = %s AND player_id = %s",
                (rules.next_day(reg["loan_end_date"]), reg["league_id"], reg["player_id"]))
    return entry


def transfer(body: dict, cur=None) -> tuple[int, dict]:
    if cur is None:
        with db.tx() as c:
            return _transfer(c, body)
    return _transfer(cur, body)


def _transfer(cur, body: dict) -> tuple[int, dict]:
    parsed = rules.validate_transfer(body)
    db.lock(cur, ROSTER_LOCK)
    clean = {k: body.get(k) for k in ("request_id", "league_id", "player_id", "type", "from_squad_id", "to_squad_id",
                                      "effective_date", "loan_end_date", "reason", "requested_by")}
    digest = crypto.body_hash(clean)
    cur.execute("SELECT body_hash, response FROM roster_requests WHERE request_id = %s", (body["request_id"],))
    prior = cur.fetchone()
    if prior:
        return 200, prior["response"]

    league, squads, regs, live = _load(cur, body["league_id"])
    decision = rules.check_transfer(body, parsed["eff"], league, squads, regs, live)
    reg = decision["reg"]
    if decision["returned"]:
        _materialize_return(cur, reg)
    state = "deferred_until_match_end" if decision["blocking"] else "active"
    t = body["type"]
    if t == "release":
        new = {"squad_id": None, "parent": None, "type": "release", "end": None, "role": None}
    elif t == "loan":
        new = {"squad_id": body["to_squad_id"], "parent": body["from_squad_id"], "type": "loan",
               "end": body["loan_end_date"], "role": "substitute"}
    else:
        new = {"squad_id": body["to_squad_id"], "parent": None, "type": "transfer", "end": None, "role": "substitute"}
    cur.execute("UPDATE registrations SET squad_id = %s, parent_squad_id = %s, role = %s, registration_type = %s,"
                " start_date = %s, loan_end_date = %s WHERE league_id = %s AND player_id = %s",
                (new["squad_id"], new["parent"], new["role"], new["type"], body["effective_date"], new["end"],
                 body["league_id"], body["player_id"]))
    entry = _write_audit(cur, {
        "action": t, "player_id": body["player_id"], "league_id": body["league_id"],
        "from_squad_id": body["from_squad_id"], "to_squad_id": body.get("to_squad_id") if t != "release" else None,
        "effective_date": body["effective_date"], "state": state, "who": body.get("requested_by"),
        "when": utc_now_iso(), "why": body.get("reason")})
    registration = None if t == "release" else {
        "player_id": body["player_id"], "league_id": body["league_id"], "squad_id": new["squad_id"],
        "parent_squad_id": new["parent"], "registration_type": new["type"], "start_date": body["effective_date"],
        "loan_end_date": new["end"], "role": new["role"]}
    response = {"request_id": body["request_id"], "status": "accepted", "state": state,
                "blocking_match_id": decision["blocking"], "registration": registration, "audit_entry": entry}
    cur.execute("INSERT INTO roster_requests (request_id, league_id, body_hash, response) VALUES (%s,%s,%s,%s)",
                (body["request_id"], body["league_id"], digest, J(response)))
    return 201, response


def player_version(cur, player_id: str) -> int | None:
    reg = _latest_registration(cur, player_id)
    if reg is None:
        return None
    cur.execute("SELECT COUNT(*) AS n FROM roster_audit WHERE league_id = %s AND player_id = %s",
                (reg["league_id"], player_id))
    return cur.fetchone()["n"]


def _latest_registration(cur, player_id: str):
    cur.execute("SELECT * FROM registrations WHERE player_id = %s ORDER BY ord DESC LIMIT 1", (player_id,))
    return cur.fetchone()


def history(player_id: str, as_of: str | None) -> dict:
    if as_of is not None and parse_date(as_of) is None:
        raise validation("as_of")
    if not is_id(player_id):
        raise not_found("PLAYER_NOT_FOUND", "Player not found.", player_id=player_id)
    on = parse_date(as_of) if as_of else date.today()
    with db.tx() as cur:
        db.lock(cur, ROSTER_LOCK)
        reg = _latest_registration(cur, player_id)
        if reg is None:
            raise not_found("PLAYER_NOT_FOUND", f"Player {player_id} not found.", player_id=player_id)
        if rules.loan_returned(reg, on):
            _materialize_return(cur, reg)
            reg = _latest_registration(cur, player_id)
        current, parent = rules.squad_on(reg, on)
        cur.execute("SELECT entry FROM roster_audit WHERE league_id = %s AND player_id = %s ORDER BY seq",
                    (reg["league_id"], player_id))
        entries = [r["entry"] for r in cur.fetchall()]
    return {"player_id": player_id, "as_of": on.isoformat(), "league_id": reg["league_id"],
            "current_squad_id": current, "parent_squad_id": parent, "history": entries}
