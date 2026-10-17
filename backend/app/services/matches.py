"""Match streams: append events to the log and rebuild projections from it."""
from .. import crypto, db
from ..db import J
from ..domain import scoring
from ..domain.scoring import Log
from ..errors import conflict, not_found
from . import realtime


def get_sport(cur, sport_id: str) -> dict | None:
    cur.execute("SELECT config FROM sports WHERE sport_id = %s", (sport_id,))
    row = cur.fetchone()
    return row["config"] if row else None


def load_log(cur, match_id: str) -> Log | None:
    cur.execute("SELECT * FROM matches WHERE match_id = %s", (match_id,))
    match = cur.fetchone()
    if match is None:
        return None
    sport = get_sport(cur, match["sport_id"])
    cur.execute("SELECT sequence, event_id, type, payload, signature FROM events WHERE match_id = %s ORDER BY sequence",
                (match_id,))
    return Log(match, sport, cur.fetchall())


def load_logs(cur, match_ids: list[str]) -> dict[str, Log]:
    if not match_ids:
        return {}
    cur.execute("SELECT * FROM matches WHERE match_id = ANY(%s)", (match_ids,))
    matches = {m["match_id"]: m for m in cur.fetchall()}
    cur.execute("SELECT match_id, sequence, event_id, type, payload, signature FROM events "
                "WHERE match_id = ANY(%s) ORDER BY match_id, sequence", (match_ids,))
    by_match: dict[str, list] = {mid: [] for mid in matches}
    for e in cur.fetchall():
        by_match[e["match_id"]].append(e)
    sports: dict[str, dict] = {}
    out = {}
    for mid, m in matches.items():
        if m["sport_id"] not in sports:
            sports[m["sport_id"]] = get_sport(cur, m["sport_id"])
        out[mid] = Log(m, sports[m["sport_id"]], by_match[mid])
    return out


def _response(row: dict) -> dict:
    return {"event_id": row["event_id"], "match_id": row["match_id"], "type": row["type"],
            "sequence": row["sequence"], "match_version": row["sequence"], "signature": row["signature"]}


def append_event(body: dict, cur=None) -> tuple[int, dict]:
    """Validate and append one event. Returns (http_status, response)."""
    scoring.validate_envelope(body)
    if cur is None:
        with db.tx() as c:
            result = _append(c, body)
    else:
        result = _append(cur, body)
    if result[0] == 201:
        realtime.publish_match(body["match_id"])
    return result


def _append(cur, body: dict) -> tuple[int, dict]:
    event_id, match_id = body["event_id"], body["match_id"]
    clean = {"event_id": event_id, "match_id": match_id, "type": body["type"], "payload": body["payload"]}
    digest = crypto.body_hash(clean)
    db.lock(cur, "event:" + event_id)
    db.lock(cur, "match:" + match_id)
    cur.execute("SELECT match_id, sequence, event_id, type, signature, body_hash FROM events WHERE event_id = %s",
                (event_id,))
    existing = cur.fetchone()
    if existing:
        if existing["body_hash"] == digest:
            return 200, _response(existing)
        raise conflict("DUPLICATE_EVENT_ID", f"Event id {event_id} was already used with a different body.",
                       event_id=event_id)

    payload = body["payload"]
    if body["type"] == "match_init":
        scoring.validate_init_payload(payload)
        if get_sport(cur, payload["sport_id"]) is None:
            raise not_found("SPORT_NOT_FOUND", f"Sport {payload['sport_id']} not found.", sport_id=payload["sport_id"])
        cur.execute("SELECT 1 FROM matches WHERE match_id = %s", (match_id,))
        if cur.fetchone():
            raise conflict("MATCH_EXISTS", f"Match {match_id} already exists.", match_id=match_id)
        cur.execute("INSERT INTO matches (match_id, sport_id, league_id, home_team_id, away_team_id, created_by_init)"
                    " VALUES (%s,%s,%s,%s,%s,TRUE)",
                    (match_id, payload["sport_id"], payload.get("league_id"), payload["home_team_id"],
                     payload["away_team_id"]))
        sequence = 1
    else:
        log = load_log(cur, match_id)
        if log is None:
            raise not_found("MATCH_NOT_FOUND", f"Match {match_id} not found.", match_id=match_id)
        if body["type"] == "compensation" and isinstance(payload.get("compensates"), str) \
                and payload["compensates"] not in log.by_id:
            cur.execute("SELECT 1 FROM events WHERE event_id = %s", (payload["compensates"],))
            if cur.fetchone():
                raise conflict("INVALID_COMPENSATION", "The target event belongs to another match.",
                               event_id=payload["compensates"])
        scoring.check_event(log, body)
        sequence = len(log.events) + 1

    signature = crypto.sign(event_id, payload)
    cur.execute("INSERT INTO events (match_id, sequence, event_id, type, payload, body_hash, signature)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (match_id, sequence, event_id, body["type"], J(payload), digest, signature))
    return 201, {"event_id": event_id, "match_id": match_id, "type": body["type"], "sequence": sequence,
                 "match_version": sequence, "signature": signature}


def score(match_id: str) -> dict:
    with db.tx() as cur:
        log = load_log(cur, match_id)
    if log is None:
        raise not_found("MATCH_NOT_FOUND", f"Match {match_id} not found.", match_id=match_id)
    return scoring.project(log)
