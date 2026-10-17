"""Autograder contract routes (/health and /audit/v1/*). Thin wrappers over domain services."""
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from .. import db, seed
from ..errors import validation
from ..http import read_object, respond

router = APIRouter()


@router.get("/health")
async def health():
    ok = await run_in_threadpool(db.ping)
    if not ok:
        return respond(503, {"error": {"code": "NOT_READY", "message": "Database not ready.", "details": {}}})
    return {"status": "ok"}


@router.post("/audit/v1/reset")
async def reset(request: Request):
    body = await read_object(request, required=False)
    seed_value = body.get("seed", 42)
    if seed_value is None:
        seed_value = 42
    if not isinstance(seed_value, int) or isinstance(seed_value, bool):
        raise validation("seed")
    stock = body.get("stock") or {}
    if not isinstance(stock, dict) or any(
            not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in stock.values()):
        raise validation("stock")
    result = await run_in_threadpool(seed.reset, seed_value, stock)
    return respond(200, result)


@router.post("/audit/v1/fixtures")
async def fixtures(request: Request):
    from ..domain.fixtures import generate
    body = await read_object(request)
    return respond(200, await run_in_threadpool(generate, body))


@router.post("/audit/v1/sports")
async def create_sport(request: Request):
    from ..services import sports as sports_service
    body = await read_object(request)
    return respond(201, await run_in_threadpool(sports_service.create, body))


@router.post("/audit/v1/events")
async def append_event(request: Request):
    from ..services import matches
    body = await read_object(request)
    status, result = await run_in_threadpool(matches.append_event, body)
    return respond(status, result)


@router.get("/audit/v1/score/{match_id}")
async def get_score(match_id: str):
    from ..services import matches
    return respond(200, await run_in_threadpool(matches.score, match_id))


@router.post("/audit/v1/leagues")
async def register_league(request: Request):
    from ..services import leagues
    body = await read_object(request)
    return respond(201, await run_in_threadpool(leagues.register, body))


@router.get("/audit/v1/standings/{league_id}")
async def get_standings(league_id: str):
    from ..services import leagues
    return respond(200, await run_in_threadpool(leagues.standings, league_id))


@router.post("/audit/v1/roster/setup")
async def roster_setup(request: Request):
    from ..services import roster
    body = await read_object(request)
    return respond(201, await run_in_threadpool(roster.setup, body))


@router.post("/audit/v1/roster/transfer")
async def roster_transfer(request: Request):
    from ..services import roster
    body = await read_object(request)
    status, result = await run_in_threadpool(roster.transfer, body)
    return respond(status, result)


@router.get("/audit/v1/roster/history/{player_id}")
async def roster_history(player_id: str, as_of: str | None = None):
    from ..services import roster
    return respond(200, await run_in_threadpool(roster.history, player_id, as_of))


@router.post("/audit/v1/checkout")
async def checkout(request: Request):
    from ..services import store
    body = await read_object(request)
    status, result = await run_in_threadpool(store.checkout, body)
    return respond(status, result)


@router.get("/audit/v1/inventory/{variant_id}")
async def inventory(variant_id: str):
    from ..services import store
    return respond(200, await run_in_threadpool(store.inventory, variant_id))


@router.post("/audit/v1/offline-sync")
async def offline_sync(request: Request):
    from ..services import sync
    body = await read_object(request)
    return respond(200, await run_in_threadpool(sync.replay, body))
