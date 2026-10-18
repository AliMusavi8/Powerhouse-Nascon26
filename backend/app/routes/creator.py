"""Creator tools for members (FR-3.1, FR-3.2, FR-3.3): athlete profile + follow graph, own stream key,
co-stream host controls. JWT required for writes; guest tokens are already stopped by the GuestWriteGuard."""
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from .. import auth, crypto, db
from ..db import J
from ..domain import scoring
from ..domain.rbac import forbidden
from ..errors import not_found, validation
from ..http import read_object, respond
from ..services import costream, matches, streams

router = APIRouter(prefix="/api/v1")


def _who(request: Request) -> dict:
    return auth.principal(request)


def _me(who: dict) -> str:
    return who.get("player_id") or who["sub"]


# ---------------------------------------------------------------- FR-3.1 athlete profile + follow graph

def _follow(follower: str, athlete: str, follow: bool) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT 1 FROM players WHERE player_id = %s", (athlete,))
        if cur.fetchone() is None:
            raise not_found("PLAYER_NOT_FOUND", f"Player {athlete} not found.", player_id=athlete)
        if follow:
            cur.execute("INSERT INTO follows (follower_id, athlete_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (follower, athlete))
        else:
            cur.execute("DELETE FROM follows WHERE follower_id = %s AND athlete_id = %s", (follower, athlete))
        cur.execute("SELECT COUNT(*) AS n FROM follows WHERE athlete_id = %s", (athlete,))
        count = int(cur.fetchone()["n"])
    return {"athlete_id": athlete, "follower_id": follower, "following": follow, "follower_count": count}


@router.post("/players/{player_id}/follow")
async def follow(request: Request, player_id: str):
    return await run_in_threadpool(_follow, _me(_who(request)), player_id, True)


@router.delete("/players/{player_id}/follow")
async def unfollow(request: Request, player_id: str):
    return await run_in_threadpool(_follow, _me(_who(request)), player_id, False)


def _profile(player_id: str, viewer: str | None) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT p.player_id, p.name, p.club_id, p.profile, c.name AS club_name FROM players p "
                    "LEFT JOIN clubs c ON c.club_id = p.club_id WHERE p.player_id = %s", (player_id,))
        p = cur.fetchone()
        if p is None:
            raise not_found("PLAYER_NOT_FOUND", f"Player {player_id} not found.", player_id=player_id)
        cur.execute("SELECT match_id FROM matches WHERE home_team_id = %s OR away_team_id = %s ORDER BY ord",
                    (p["club_id"], p["club_id"]))
        logs = matches.load_logs(cur, [r["match_id"] for r in cur.fetchall()])
        cur.execute("SELECT COUNT(*) AS n FROM follows WHERE athlete_id = %s", (player_id,))
        followers = int(cur.fetchone()["n"])
        following = False
        if viewer:
            cur.execute("SELECT 1 FROM follows WHERE follower_id = %s AND athlete_id = %s", (viewer, player_id))
            following = cur.fetchone() is not None
        cur.execute("SELECT stream_key FROM stream_keys WHERE player_id = %s", (player_id,))
        keys = [r["stream_key"] for r in cur.fetchall()]
        cur.execute("SELECT vod_id, object_key, created_at FROM vods WHERE stream_key = ANY(%s) ORDER BY created_at DESC",
                    (keys,))
        vods = [{"vod_id": v["vod_id"], "object_key": v["object_key"], "created_at": v["created_at"].isoformat()}
                for v in cur.fetchall()]
    record = {"played": 0, "won": 0, "drawn": 0, "lost": 0}
    upcoming = []
    for mid, log in logs.items():
        if log.status == "completed":
            result, winner = scoring.outcome(log)
            record["played"] += 1
            if winner == p["club_id"]:
                record["won"] += 1
            elif result == "draw":
                record["drawn"] += 1
            else:
                record["lost"] += 1
        elif log.status == "upcoming":
            upcoming.append({"match_id": mid, "scheduled_at": log.match.get("scheduled_at"),
                             "home_team_id": log.match["home_team_id"], "away_team_id": log.match["away_team_id"]})
    return {"player_id": player_id, "name": p["name"], "profile": p["profile"],
            "affiliations": [{"club_id": p["club_id"], "name": p["club_name"], "active": True}] if p["club_id"] else [],
            "career": record, "upcoming_fixtures": upcoming, "vods": vods, "follower_count": followers,
            "following": following}


@router.get("/players/{player_id}/profile")
async def profile(request: Request, player_id: str):
    viewer = None
    try:
        viewer = _me(_who(request))
    except Exception:
        pass  # public profile; guests see it without the "following" flag
    return await run_in_threadpool(_profile, player_id, viewer)


# ---------------------------------------------------------------- FR-3.2 member stream key

@router.post("/streams/key")
async def my_stream_key(request: Request):
    who = _who(request)
    if not who.get("player_id"):
        raise forbidden("Only athletes can broadcast.")
    body = await read_object(request)
    req = {"action": body.get("action", "generate"), "player_id": who["player_id"], "label": body.get("label")}
    status, result = await run_in_threadpool(streams.handle, req)
    return respond(status, result)


# ---------------------------------------------------------------- FR-3.3 co-stream host controls

CONTROLS = ("mute", "unmute", "spotlight", "kick")


def _control(sid: str, actor: str, role: str, body: dict) -> dict:
    action, target = body.get("action"), body.get("player_id")
    if action not in CONTROLS or not isinstance(target, str):
        raise validation(["action", "player_id"])
    with db.tx() as cur:
        db.lock(cur, "costream:" + sid)
        cur.execute("SELECT state FROM costream_sessions WHERE session_id = %s", (sid,))
        row = cur.fetchone()
        if row is None:
            raise not_found("STREAM_NOT_FOUND", f"Co-stream {sid} not found.", session_id=sid)
        state = row["state"]
        if role != "super_admin" and state.get("active_host") != actor:
            raise forbidden("Only the active host can moderate this co-stream.")
        if target not in state["active_participants"]:
            raise not_found("PLAYER_NOT_FOUND", f"Player {target} is not live in this co-stream.", player_id=target)
        muted = set(state.get("muted", []))
        if action == "mute":
            muted.add(target)
        elif action == "unmute":
            muted.discard(target)
        elif action == "spotlight":
            state["active_participants"] = [target] + [p for p in state["active_participants"] if p != target]
            state["layout"] = "spotlight"
        elif action == "kick":
            if target == state["active_host"]:
                raise validation("player_id", "The host cannot kick themselves.")
            state["active_participants"] = [p for p in state["active_participants"] if p != target]
            state["participant_count"] = len(state["active_participants"])
            muted.discard(target)
        state["muted"] = sorted(muted)
        response = costream._finish(sid, state)
        response["muted"] = state["muted"]
        cur.execute("UPDATE costream_sessions SET state = %s, response = %s, body_hash = '', updated_at = now() "
                    "WHERE session_id = %s", (J(state), J(response), sid))
    costream._changed(sid, response)
    return response


@router.post("/costream/{session_id}/control")
async def costream_control(request: Request, session_id: str):
    who = _who(request)
    body = await read_object(request)
    return await run_in_threadpool(_control, session_id, _me(who), who.get("role"), body)


def _invite(sid: str, actor: str, role: str, invitee) -> dict:
    if not isinstance(invitee, str):
        raise validation("player_id")
    row = costream.get(sid)
    if row is None:
        raise not_found("STREAM_NOT_FOUND", f"Co-stream {sid} not found.", session_id=sid)
    if role != "super_admin" and row["state"].get("active_host") != actor:
        raise forbidden("Only the active host can invite squad members.")
    payload = {"invitee": invitee, "session_id": sid}
    token = "inv_" + crypto.sign_day2(sid, payload)[:32]
    from ..services import realtime
    realtime.publish("costream:" + sid, {"type": "costream_invite", "session_id": sid, "invitee": invitee})
    from ..services import notify
    notify.dispatch("costream_invite", "player:" + invitee, {"session_id": sid, "deep_link": f"nascon://stream/{sid}"})
    return {"session_id": sid, "invitee": invitee, "invite_token": token, "deep_link": f"nascon://stream/{sid}"}


@router.post("/costream/{session_id}/invite")
async def costream_invite(request: Request, session_id: str):
    who = _who(request)
    body = await read_object(request)
    return await run_in_threadpool(_invite, session_id, _me(who), who.get("role"), body.get("player_id"))
