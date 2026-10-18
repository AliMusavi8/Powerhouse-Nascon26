"""Zero-account guest API (FR-4.2) used by the Guest Web Player, live chat (FR-5.3) and realtime streams (NFR-1).

Guest reads need no credentials (or a guest_* token). Every write a guest attempts is stopped earlier by the
GuestWriteGuard middleware; the member-only writes here additionally require a JWT.
"""
import asyncio
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from .. import auth, config, db
from ..domain.guest import bearer, guest_forbidden, is_guest_token
from ..errors import not_found
from ..http import read_object
from ..services import guestcart, matches, moderation, realtime

router = APIRouter(prefix="/api/v1")
ws_router = APIRouter()


# ---------------------------------------------------------------- guest reads

@router.post("/guest/session")
async def guest_session():
    return await run_in_threadpool(guestcart.new_session)


def _product(cur, product_id: str | None) -> dict | None:
    if not product_id:
        return None
    cur.execute("SELECT product_id, data FROM products WHERE product_id = %s", (product_id,))
    p = cur.fetchone()
    if p is None:
        return None
    cur.execute("SELECT variant_id, price_minor, currency, stock, attributes FROM variants WHERE product_id = %s "
                "ORDER BY variant_id", (product_id,))
    return {"product_id": p["product_id"], **p["data"], "variants": cur.fetchall()}


def _playback(path: str) -> dict:
    return {"hls": f"{config.MEDIA_HLS_BASE}/{path}/index.m3u8", "whep": f"{config.MEDIA_WEBRTC_BASE}/{path}/whep"}


def match_summary(match_id: str) -> dict:
    with db.tx() as cur:
        log = matches.load_log(cur, match_id)
        if log is None:
            raise not_found("MATCH_NOT_FOUND", f"Match {match_id} not found.", match_id=match_id)
        from ..domain import scoring
        p = scoring.project(log)
        cur.execute("SELECT club_id, name FROM clubs WHERE club_id = ANY(%s)", ([p["home"]["team_id"],
                                                                                p["away"]["team_id"]],))
        names = {r["club_id"]: r["name"] for r in cur.fetchall()}
        pinned = _product(cur, log.match.get("pinned_product_id") or "prod-jersey-001")
        key = log.match.get("live_stream_key")
    side = lambda s: {"team_id": p[s]["team_id"], "name": names.get(p[s]["team_id"], p[s]["team_id"]),
                      "score": p[s]["score"]}
    return {"match_id": match_id, "status": p["status"], "home": side("home"), "away": side("away"),
            "version": p["version"], "scheduled_at": log.match.get("scheduled_at"), "venue": log.match.get("venue"),
            "pinned_product": pinned, "chat_room_id": f"chat-{match_id}",
            "playback": _playback(f"live/{key}" if key else f"matchfeed/{match_id}")}


@router.get("/guest/matches/{match_id}")
async def guest_match(match_id: str):
    return await run_in_threadpool(match_summary, match_id)


def costream_summary(session_id: str) -> dict:
    from ..services import costream
    row = costream.get(session_id)
    if row is None:
        raise not_found("STREAM_NOT_FOUND", f"Co-stream {session_id} not found.", session_id=session_id)
    with db.tx() as cur:
        cur.execute("SELECT player_id, name FROM players WHERE player_id = ANY(%s)", (row["state"]["participants"],))
        names = {r["player_id"]: r["name"] for r in cur.fetchall()}
    out = {k: v for k, v in row["response"].items() if k != "signature"}
    out["names"] = names
    out["playback"] = _playback(f"costream/{session_id}")
    return out


@router.get("/guest/costream/{session_id}")
async def guest_costream(session_id: str):
    return await run_in_threadpool(costream_summary, session_id)


@router.get("/guest/chat/{room}")
async def guest_chat(room: str):
    return await run_in_threadpool(moderation.history, room)


@router.post("/guest/cart")
async def guest_cart_stage(request: Request):
    body = await read_object(request)
    return await run_in_threadpool(guestcart.stage, bearer(request.headers.get("authorization")), body)


# ---------------------------------------------------------------- member writes

def _member(request: Request) -> dict:
    token = bearer(request.headers.get("authorization"))
    if token is None or is_guest_token(token):
        raise guest_forbidden(token)  # unauthenticated guest sessions are read-only (FR-4.3)
    return auth.decode_token(token)


@router.post("/chat")
async def post_chat(request: Request):
    who = _member(request)
    body = await read_object(request)
    sender = who.get("player_id") or who["sub"]
    return await run_in_threadpool(moderation.post, body.get("chat_room_id"), sender, body.get("text"))


@router.post("/cart/merge")
async def member_cart_merge(request: Request):
    who = _member(request)
    body = await read_object(request)
    merged = {"guest_token": body.get("guest_token"), "registered_user_id": who.get("player_id") or who["sub"],
              "guest_cart": body.get("guest_cart"), "test_write_block": False}
    if not merged["guest_cart"]:
        merged["guest_cart"] = await run_in_threadpool(_staged, body.get("guest_token"))
    status, result = await run_in_threadpool(guestcart.merge, merged)
    return result


def _staged(token) -> list:
    with db.tx() as cur:
        cur.execute("SELECT cart FROM guest_tokens WHERE guest_token = %s", (token,))
        row = cur.fetchone()
    return row["cart"] if row else []


# ---------------------------------------------------------------- realtime: SSE + WebSockets

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


@router.get("/matches/{match_id}/stream")
async def match_stream(match_id: str):
    snapshot = await run_in_threadpool(match_summary, match_id)
    topics = ["match:" + match_id, f"chat:chat-{match_id}"]

    async def events():
        queues = [realtime.subscribe(t) for t in topics]
        realtime.connection_opened()
        merged: asyncio.Queue = asyncio.Queue()

        async def pump(q):
            while True:
                await merged.put(await q.get())

        tasks = [asyncio.create_task(pump(q)) for q in queues]
        try:
            yield "retry: 1000\n\n"
            yield _sse({"type": "snapshot", **snapshot})
            while True:
                try:
                    yield _sse(await asyncio.wait_for(merged.get(), timeout=15))
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            for t in tasks:
                t.cancel()
            for t, q in zip(topics, queues):
                realtime.unsubscribe(t, q)
            realtime.connection_closed()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _relay(ws: WebSocket, topic: str, hello: dict) -> None:
    await ws.accept()
    q = realtime.subscribe(topic)
    realtime.connection_opened()
    try:
        await ws.send_json(hello)
        receiver = asyncio.create_task(ws.receive_text())
        while True:
            getter = asyncio.create_task(q.get())
            done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
            if receiver in done:
                getter.cancel()
                receiver.result()  # raises WebSocketDisconnect when the client leaves
                receiver = asyncio.create_task(ws.receive_text())
                continue
            await ws.send_json(getter.result())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        realtime.unsubscribe(topic, q)
        realtime.connection_closed()


@ws_router.websocket("/ws/chat/{room}")
async def chat_socket(ws: WebSocket, room: str):
    await _relay(ws, "chat:" + room, {"type": "subscribed", "chat_room_id": room})


@ws_router.websocket("/ws/costream/{session_id}")
async def costream_socket(ws: WebSocket, session_id: str):
    """Participants connect with ?player_id=; if the active host's socket drops, hosting moves on (FR-3.3)."""
    from ..services import costream
    player_id = ws.query_params.get("player_id")
    try:
        await _relay(ws, "costream:" + session_id, {"type": "subscribed", "session_id": session_id})
    finally:
        if player_id:
            await asyncio.sleep(0.5)
            await run_in_threadpool(costream.host_disconnected, session_id, player_id)
