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
