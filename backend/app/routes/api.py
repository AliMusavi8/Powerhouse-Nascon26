"""Production API used by the mobile app (/api/v1/*). Rate limited; JWT + RBAC on every data route.

Domain logic is shared with the /audit/v1 routes: the same services and rules back both.
"""
import secrets

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .. import auth, db
from ..domain import scoring
from ..domain.rbac import allowed, forbidden, require
from ..domain.validate import is_id, utc_now_iso
from ..errors import not_found, validation
from ..http import read_object, respond
from ..services import leagues, matches, realtime, roster, store, sync

router = APIRouter(prefix="/api/v1")
ws_router = APIRouter()


@router.get("/ping")
async def ping():
    return {"pong": True}


# ---------------------------------------------------------------- auth

@router.post("/auth/login")
async def login(request: Request):
    body = await read_object(request)
    return await run_in_threadpool(auth.login, body.get("email"), body.get("password"))


def _tenant(tenant_id):
    with db.tx() as cur:
        cur.execute("SELECT tenant_id, name, branding FROM tenants WHERE tenant_id = %s", (tenant_id,))
        return cur.fetchone()


@router.get("/me")
async def me(request: Request):
    who = auth.principal(request)
    tenant = await run_in_threadpool(_tenant, who.get("tenant_id") or "tenant-alpha")
    return {"user": {k: who.get(k) for k in ("sub", "email", "role", "tenant_id", "league_id", "club_id", "player_id")},
            "tenant": tenant, "permissions": _permissions(who)}


def _permissions(who: dict) -> dict:
    role = who.get("role")
    return {"score_entry": role in ("super_admin", "league_organizer"),
            "roster_management": role in ("super_admin", "club_manager"),
            "store": True, "admin": role == "super_admin"}


# ---------------------------------------------------------------- leagues, fixtures, standings

def _club_names(cur) -> dict:
    cur.execute("SELECT club_id, name FROM clubs")
    return {r["club_id"]: r["name"] for r in cur.fetchall()}


def _list_leagues(who: dict) -> list[dict]:
    with db.tx() as cur:
        if who["role"] == "super_admin":
            cur.execute("SELECT league_id, tenant_id, sport_id, name FROM leagues WHERE tenant_id IS NOT NULL ORDER BY league_id")
        else:
            cur.execute("SELECT league_id, tenant_id, sport_id, name FROM leagues WHERE tenant_id = %s ORDER BY league_id",
                        (who.get("tenant_id"),))
        rows = cur.fetchall()
        cur.execute("SELECT league_id, COUNT(*) AS n FROM matches WHERE league_id IS NOT NULL GROUP BY league_id")
        counts = {r["league_id"]: r["n"] for r in cur.fetchall()}
    return [dict(r, fixture_count=counts.get(r["league_id"], 0)) for r in rows]


@router.get("/leagues")
async def list_leagues(request: Request):
    who = auth.principal(request)
    return {"leagues": await run_in_threadpool(_list_leagues, who)}


def _league_guard(who: dict, league_id: str) -> None:
    require(who, "league.read", auth.league_target(league_id))


def _fixtures(league_id: str) -> list[dict]:
    with db.tx() as cur:
        cur.execute("SELECT match_id FROM matches WHERE league_id = %s ORDER BY scheduled_at NULLS LAST, ord", (league_id,))
        ids = [r["match_id"] for r in cur.fetchall()]
        logs = matches.load_logs(cur, ids)
        names = _club_names(cur)
    out = []
    for mid in ids:
        log = logs[mid]
        p = scoring.project(log)
        m = log.match
        out.append({"match_id": mid, "league_id": league_id, "sport_id": m["sport_id"],
                    "home": {"team_id": p["home"]["team_id"], "name": names.get(p["home"]["team_id"], p["home"]["team_id"]),
                             "score": p["home"]["score"]},
                    "away": {"team_id": p["away"]["team_id"], "name": names.get(p["away"]["team_id"], p["away"]["team_id"]),
                             "score": p["away"]["score"]},
                    "status": p["status"], "outcome": p["outcome"], "scheduled_at": m.get("scheduled_at"),
                    "venue": m.get("venue"), "version": p["version"]})
    return out


@router.get("/leagues/{league_id}/fixtures")
async def league_fixtures(request: Request, league_id: str):
    who = auth.principal(request)
    await run_in_threadpool(_league_guard, who, league_id)
    return {"league_id": league_id, "fixtures": await run_in_threadpool(_fixtures, league_id)}


def _standings(league_id: str) -> dict:
    out = leagues.standings(league_id)
    with db.tx() as cur:
        names = _club_names(cur)
    for row in out["table"]:
        row["name"] = names.get(row["team_id"], row["team_id"])
    return out


@router.get("/leagues/{league_id}/standings")
async def league_standings(request: Request, league_id: str):
    who = auth.principal(request)
    await run_in_threadpool(_league_guard, who, league_id)
    return await run_in_threadpool(_standings, league_id)


# ---------------------------------------------------------------- matches

def _match_detail(who: dict, match_id: str) -> dict:
    with db.tx() as cur:
        log = matches.load_log(cur, match_id)
        if log is None:
            raise not_found("MATCH_NOT_FOUND", f"Match {match_id} not found.", match_id=match_id)
        names = _club_names(cur)
        league = None
        if log.match.get("league_id"):
            cur.execute("SELECT tenant_id FROM leagues WHERE league_id = %s", (log.match["league_id"],))
            league = cur.fetchone()
        pinned = None
        if log.match.get("pinned_product_id"):
            pinned = _product(cur, log.match["pinned_product_id"])
    target = {"tenant_id": league["tenant_id"] if league else who.get("tenant_id"), "league_id": log.match.get("league_id")}
    require(who, "league.read", target)
    p = scoring.project(log)
    for side in ("home", "away"):
        p[side]["name"] = names.get(p[side]["team_id"], p[side]["team_id"])
    p["scheduled_at"], p["venue"] = log.match.get("scheduled_at"), log.match.get("venue")
    p["pinned_product"] = pinned
    p["scoring_events"] = sorted(log.sport["scoring_events"].keys())
    p["can_score"] = allowed(who, "match.score.write", target)
    return p


@router.get("/matches/{match_id}")
async def match_detail(request: Request, match_id: str):
    who = auth.principal(request)
    return await run_in_threadpool(_match_detail, who, match_id)


def _score_guard(who: dict, match_id: str) -> None:
    with db.tx() as cur:
        cur.execute("SELECT m.league_id, l.tenant_id FROM matches m LEFT JOIN leagues l ON l.league_id = m.league_id "
                    "WHERE m.match_id = %s", (match_id,))
        row = cur.fetchone()
    if row is None:
        raise not_found("MATCH_NOT_FOUND", f"Match {match_id} not found.", match_id=match_id)
    require(who, "match.score.write", {"tenant_id": row["tenant_id"], "league_id": row["league_id"]})


@router.post("/matches/{match_id}/events")
async def match_event(request: Request, match_id: str):
    who = auth.principal(request)
    body = await read_object(request)
    await run_in_threadpool(_score_guard, who, match_id)
    body = {"event_id": body.get("event_id") or "app-" + secrets.token_hex(8), "match_id": match_id,
            "type": body.get("type"), "payload": body.get("payload") if isinstance(body.get("payload"), dict) else {}}
    status, result = await run_in_threadpool(matches.append_event, body)
    return respond(status, result)


def _pin(who: dict, match_id: str, product_id) -> dict:
    if not is_id(product_id):
        raise validation("product_id")
    with db.tx() as cur:
        cur.execute("SELECT m.league_id, l.tenant_id FROM matches m LEFT JOIN leagues l ON l.league_id = m.league_id "
                    "WHERE m.match_id = %s", (match_id,))
        row = cur.fetchone()
        if row is None:
            raise not_found("MATCH_NOT_FOUND", f"Match {match_id} not found.", match_id=match_id)
        require(who, "match.pin_product", {"tenant_id": row["tenant_id"], "league_id": row["league_id"]})
        product = _product(cur, product_id)
        if product is None:
            raise not_found("PRODUCT_NOT_FOUND", f"Product {product_id} not found.", product_id=product_id)
        cur.execute("UPDATE matches SET pinned_product_id = %s WHERE match_id = %s", (product_id, match_id))
    realtime.publish("match:" + match_id, {"type": "product_pinned", "match_id": match_id, "product": product})
    return {"match_id": match_id, "pinned_product": product}


@router.post("/matches/{match_id}/pinned-product")
async def pin_product(request: Request, match_id: str):
    who = auth.principal(request)
    body = await read_object(request)
    return await run_in_threadpool(_pin, who, match_id, body.get("product_id"))


# ---------------------------------------------------------------- clubs and roster

def _list_clubs(who: dict) -> list[dict]:
    with db.tx() as cur:
        if who["role"] == "super_admin":
            cur.execute("SELECT club_id, tenant_id, league_id, name FROM clubs ORDER BY name")
        else:
            cur.execute("SELECT club_id, tenant_id, league_id, name FROM clubs WHERE tenant_id = %s ORDER BY name",
                        (who.get("tenant_id"),))
        return cur.fetchall()


@router.get("/clubs")
async def list_clubs(request: Request):
    who = auth.principal(request)
    return {"clubs": await run_in_threadpool(_list_clubs, who)}


def _club_detail(who: dict, club_id: str) -> dict:
    target = auth.club_target(club_id)
    require(who, "club.read", target)
    with db.tx() as cur:
        cur.execute("SELECT * FROM clubs WHERE club_id = %s", (club_id,))
        club = cur.fetchone()
        cur.execute("SELECT r.player_id, r.name, r.position, r.role, r.registration_type, r.parent_squad_id,"
                    " r.loan_end_date, r.league_id FROM registrations r WHERE r.squad_id = %s ORDER BY r.name", (club_id,))
        players = cur.fetchall()
        cur.execute("SELECT squad_id, name FROM squads WHERE league_id = %s AND squad_id <> %s ORDER BY name",
                    (club["league_id"], club_id))
        other_squads = cur.fetchall()
        cur.execute("SELECT entry FROM roster_audit WHERE league_id = %s AND (entry->>'from_squad_id' = %s OR "
                    "entry->>'to_squad_id' = %s) ORDER BY seq DESC LIMIT 20", (club["league_id"], club_id, club_id))
        recent = [r["entry"] for r in cur.fetchall()]
        tenant = _tenant(club["tenant_id"])
    profile = club["profile"]
    return {"club_id": club_id, "name": club["name"], "tenant": tenant, "league_id": club["league_id"],
            "home_venue": profile.get("home_venue"), "socials": profile.get("socials", {}),
            "staff": profile.get("staff", []), "history": profile.get("history", []),
            "roster": players, "other_squads": other_squads, "recent_moves": recent,
            "can_manage": allowed(who, "club.roster.write", target)}


@router.get("/clubs/{club_id}")
async def club_detail(request: Request, club_id: str):
    who = auth.principal(request)
    return await run_in_threadpool(_club_detail, who, club_id)


def _club_transfer(who: dict, club_id: str, body: dict):
    require(who, "club.roster.write", auth.club_target(club_id))
    with db.tx() as cur:
        cur.execute("SELECT league_id FROM clubs WHERE club_id = %s", (club_id,))
        league_id = cur.fetchone()["league_id"]
    full = {"request_id": body.get("request_id") or "app-" + secrets.token_hex(8), "league_id": league_id,
            "player_id": body.get("player_id"), "type": body.get("type"), "from_squad_id": club_id,
            "to_squad_id": body.get("to_squad_id"), "effective_date": body.get("effective_date") or utc_now_iso()[:10],
            "loan_end_date": body.get("loan_end_date"), "reason": body.get("reason") or "Club manager action",
            "requested_by": who.get("email") or who.get("sub")}
    return roster.transfer(full)


@router.post("/clubs/{club_id}/roster/transfer")
async def club_transfer(request: Request, club_id: str):
    who = auth.principal(request)
    body = await read_object(request)
    status, result = await run_in_threadpool(_club_transfer, who, club_id, body)
    return respond(status, result)


def _add_player(who: dict, club_id: str, body: dict) -> dict:
    target = auth.club_target(club_id)
    require(who, "club.roster.write", target)
    name, position, role = body.get("name"), body.get("position"), body.get("role") or "substitute"
    bad = [f for f, ok in (("name", isinstance(name, str) and 1 <= len(name.strip()) <= 80),
                           ("position", isinstance(position, str) and 1 <= len(position) <= 20),
                           ("role", role in ("captain", "vice_captain", "starter", "substitute"))) if not ok]
    if bad:
        raise validation(bad)
    pid = "pl-" + secrets.token_hex(5)
    with db.tx() as cur:
        db.lock(cur, roster.ROSTER_LOCK)
        cur.execute("SELECT league_id FROM clubs WHERE club_id = %s", (club_id,))
        league_id = cur.fetchone()["league_id"]
        cur.execute("SELECT config FROM roster_leagues WHERE league_id = %s", (league_id,))
        cfg = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS n FROM registrations WHERE squad_id = %s AND league_id = %s", (club_id, league_id))
        if cfg and cur.fetchone()["n"] + 1 > cfg["config"]["max_squad_size"]:
            from ..errors import conflict
            raise conflict("SQUAD_FULL", "The squad is full.", squad_id=club_id)
        cur.execute("INSERT INTO players (player_id, tenant_id, club_id, name, profile) VALUES (%s,%s,%s,%s,%s)",
                    (pid, target["tenant_id"], club_id, name.strip(), db.J({"position": position, "role": role})))
        cur.execute("INSERT INTO registrations (league_id, player_id, name, position, squad_id, role, registration_type,"
                    " start_date) VALUES (%s,%s,%s,%s,%s,%s,'initial',%s)",
                    (league_id, pid, name.strip(), position, club_id, role, utc_now_iso()[:10]))
        entry = roster._write_audit(cur, {
            "action": "register", "player_id": pid, "league_id": league_id, "from_squad_id": None,
            "to_squad_id": club_id, "effective_date": utc_now_iso()[:10], "state": "active",
            "who": who.get("email") or who.get("sub"), "when": utc_now_iso(), "why": "Player added by club manager"})
    return {"player_id": pid, "name": name.strip(), "position": position, "role": role, "audit_entry": entry}


@router.post("/clubs/{club_id}/players")
async def add_player(request: Request, club_id: str):
    who = auth.principal(request)
    body = await read_object(request)
    return respond(201, await run_in_threadpool(_add_player, who, club_id, body))


@router.get("/players/{player_id}/history")
async def player_history(request: Request, player_id: str):
    who = auth.principal(request)
    target = await run_in_threadpool(auth.player_target, player_id)
    require(who, "club.read", target)
    return await run_in_threadpool(roster.history, player_id, None)


# ---------------------------------------------------------------- store

def _product(cur, product_id: str) -> dict | None:
    cur.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
    p = cur.fetchone()
    if p is None:
        return None
    cur.execute("SELECT variant_id, price_minor, currency, stock, attributes FROM variants WHERE product_id = %s "
                "ORDER BY variant_id", (product_id,))
    return {"product_id": p["product_id"], "tenant_id": p["tenant_id"], "club_id": p["club_id"], **p["data"],
            "variants": cur.fetchall()}


def _products(who: dict) -> list[dict]:
    with db.tx() as cur:
        if who["role"] == "super_admin":
            cur.execute("SELECT product_id FROM products ORDER BY product_id")
        else:
            cur.execute("SELECT product_id FROM products WHERE tenant_id = %s ORDER BY product_id", (who.get("tenant_id"),))
        return [_product(cur, r["product_id"]) for r in cur.fetchall()]


@router.get("/products")
async def products(request: Request):
    who = auth.principal(request)
    return {"products": await run_in_threadpool(_products, who)}


def _buy(who: dict, body: dict):
    items = body.get("items")
    if isinstance(items, list):
        with db.tx() as cur:
            ids = [i.get("variant_id") for i in items if isinstance(i, dict)]
            cur.execute("SELECT DISTINCT p.tenant_id FROM variants v JOIN products p ON p.product_id = v.product_id "
                        "WHERE v.variant_id = ANY(%s)", (ids,))
            for r in cur.fetchall():
                require(who, "store.buy", {"tenant_id": r["tenant_id"]})
    order = {"order_id": body.get("order_id") or "app-" + secrets.token_hex(8),
             "customer_id": who.get("email") or who.get("sub"), "items": items,
             "discount_code": body.get("discount_code") or None, "payment": body.get("payment")}
    return store.checkout(order)


@router.post("/checkout")
async def checkout(request: Request):
    who = auth.principal(request)
    body = await read_object(request)
    status, result = await run_in_threadpool(_buy, who, body)
    return respond(status, result)


def _my_orders(who: dict) -> list[dict]:
    with db.tx() as cur:
        cur.execute("SELECT order_id, status, response, created_at FROM orders WHERE customer_id = %s "
                    "ORDER BY created_at DESC", (who.get("email") or who.get("sub"),))
        rows = cur.fetchall()
    return [{"order_id": r["order_id"], "status": r["status"], "total_minor": r["response"]["total_minor"],
             "items": r["response"]["items"], "paid_at": r["response"]["receipt"]["payload"]["paid_at"]} for r in rows]


@router.get("/orders")
async def orders(request: Request):
    who = auth.principal(request)
    return {"orders": await run_in_threadpool(_my_orders, who)}


def _receipt(who: dict, order_id: str):
    pdf, resp = store.receipt(order_id)
    owner = resp["receipt"]["payload"]["customer_id"]
    if who["role"] != "super_admin" and owner not in (who.get("email"), who.get("sub")):
        raise forbidden()
    return pdf


@router.get("/orders/{order_id}/receipt.pdf")
async def receipt_pdf(request: Request, order_id: str):
    who = auth.principal(request)
    pdf = await run_in_threadpool(_receipt, who, order_id)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="receipt-{order_id}.pdf"'})


@router.post("/orders/{order_id}/status")
async def order_status(request: Request, order_id: str):
    who = auth.principal(request)
    body = await read_object(request)
    if who["role"] not in ("super_admin", "club_manager"):
        raise forbidden()
    target = body.get("status")
    if target not in ("packed", "shipped", "delivered", "cancelled", "refunded"):
        raise validation("status")
    return await run_in_threadpool(store.transition, order_id, target)


# ---------------------------------------------------------------- offline sync

def _sync_guard(who: dict, body: dict) -> None:
    for a in body.get("actions") or []:
        if not isinstance(a, dict) or not isinstance(a.get("payload"), dict):
            continue
        if a.get("type") == "score_event" and isinstance(a["payload"].get("match_id"), str):
            try:
                _score_guard(who, a["payload"]["match_id"])
            except Exception as exc:  # unknown match is reported per action by the sync engine
                if getattr(exc, "status", None) == 403:
                    raise
        if a.get("type") == "roster_transfer" and is_id(a["payload"].get("from_squad_id")):
            try:
                require(who, "club.roster.write", auth.club_target(a["payload"]["from_squad_id"]))
            except Exception as exc:
                if getattr(exc, "status", None) == 403:
                    raise


@router.post("/sync")
async def offline_sync(request: Request):
    who = auth.principal(request)
    body = await read_object(request)
    await run_in_threadpool(_sync_guard, who, body)
    return await run_in_threadpool(sync.replay, body)


# ---------------------------------------------------------------- realtime

@ws_router.websocket("/ws/matches/{match_id}")
async def match_socket(ws: WebSocket, match_id: str):
    token = ws.query_params.get("token", "")
    try:
        auth.decode_token(token)
    except Exception:
        await ws.close(code=4401)
        return
    await ws.accept()
    q = realtime.subscribe("match:" + match_id)
    try:
        await ws.send_json({"type": "subscribed", "match_id": match_id})
        while True:
            msg = await q.get()
            await ws.send_json(msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        realtime.unsubscribe("match:" + match_id, q)
