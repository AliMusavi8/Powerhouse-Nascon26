"""RBAC matrix and authorization probe routes (spec 5.13). Probes never mutate and never read the body."""
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from .. import auth
from ..domain.rbac import require

router = APIRouter()
OK = {"authorized": True}


@router.post("/audit/v1/rbac-matrix")
async def rbac_matrix():
    tokens = await run_in_threadpool(auth.tokens_for_demo_users)
    return {"tokens": tokens, "context": {
        "tenant_id": "tenant-alpha", "foreign_tenant_id": "tenant-beta",
        "own_league_id": "league-alpha-1", "other_league_id": "league-alpha-2", "foreign_league_id": "league-beta-1",
        "own_club_id": "club-alpha-1", "other_club_id": "club-alpha-2", "foreign_club_id": "club-beta-1",
        "own_player_id": "player-alpha-1", "other_player_id": "player-alpha-2", "foreign_player_id": "player-beta-1"}}


async def _check(request: Request, action: str, target_fn=None, target_id: str | None = None):
    who = auth.principal(request)
    target = await run_in_threadpool(target_fn, target_id) if target_fn else None
    require(who, action, target)
    return OK


@router.post("/audit/v1/rbac/tenants")
async def probe_tenants(request: Request):
    return await _check(request, "tenant.create")


@router.post("/audit/v1/rbac/leagues/{league_id}/fixtures")
async def probe_fixtures(request: Request, league_id: str):
    return await _check(request, "league.fixtures.write", auth.league_target, league_id)


@router.post("/audit/v1/rbac/clubs/{club_id}/roster")
async def probe_roster(request: Request, club_id: str):
    return await _check(request, "club.roster.write", auth.club_target, club_id)


@router.post("/audit/v1/rbac/clubs/{club_id}/products")
async def probe_products(request: Request, club_id: str):
    return await _check(request, "club.products.write", auth.club_target, club_id)


@router.patch("/audit/v1/rbac/players/{player_id}")
async def probe_player(request: Request, player_id: str):
    return await _check(request, "player.update", auth.player_target, player_id)


@router.get("/audit/v1/rbac/clubs/{club_id}")
async def probe_club_read(request: Request, club_id: str):
    return await _check(request, "club.read", auth.club_target, club_id)


@router.get("/audit/v1/rbac/platform/config")
async def probe_platform(request: Request):
    return await _check(request, "platform.config")
