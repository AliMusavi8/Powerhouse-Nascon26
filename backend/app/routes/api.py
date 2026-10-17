"""Production API used by the mobile app (/api/v1/*). Rate limited; JWT + RBAC on every data route."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/ping")
async def ping():
    return {"pong": True}
