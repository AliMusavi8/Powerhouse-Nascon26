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
