"""FastAPI application: middleware, error envelope and router wiring."""
import logging
import threading
import time
from collections import deque

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config, db, seed
from .errors import ApiError
from .routes import api, audit, creator, day2, guest, rbac, web

log = logging.getLogger("nascon")

app = FastAPI(title="NaSCon League Platform", version="1.0.0")


@app.on_event("startup")
async def _bind_realtime() -> None:
    import asyncio
    from .services import realtime
    realtime.bind_loop(asyncio.get_running_loop())


@app.on_event("startup")
def _startup() -> None:
    db.wait_for_db()
    db.create_schema()
    if not db.ping():
        seed.reset()


# ---------------------------------------------------------------- error envelope

@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=exc.body(), headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    fields = [str(e["loc"][-1]) for e in exc.errors() if e.get("loc")]
    return JSONResponse(status_code=400, content={"error": {
        "code": "VALIDATION_ERROR", "message": "Request validation failed.", "details": {"fields": fields}}})


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException):
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(status_code=exc.status_code,
                        content={"error": {"code": code, "message": str(exc.detail), "details": {}}})


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception):
    log.exception("unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": {
        "code": "INTERNAL_ERROR", "message": "Unexpected server error.", "details": {}}})


# ---------------------------------------------------------------- body limit + rate limit (pure ASGI, cheap)

_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()


def _rate_limited(path: str, client) -> int | None:
    """Seconds to wait if this /api/v1/* request is over the per-IP limit, else None."""
    if not path.startswith("/api/v1/") or path.startswith("/api/v1/guest/") or path.endswith("/stream"):
        return None
    ip = client[0] if client else "unknown"
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW_SECONDS
    with _hits_lock:
        q = _hits.setdefault(ip, deque())
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= config.RATE_LIMIT_REQUESTS:
            return max(1, int(window - (now - q[0])) + 1)
        q.append(now)
    return None


class LimitsMiddleware:
    """1 MB body limit (413) on every route, and 100 requests / 10 s per IP on /api/v1/* (429)."""

    def __init__(self, app):
        self.inner = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            length = next((v for k, v in scope["headers"] if k == b"content-length"), b"")
            if length.isdigit() and int(length) > config.MAX_BODY_BYTES:
                await JSONResponse(status_code=413, content={"error": {
                    "code": "PAYLOAD_TOO_LARGE", "message": "Request body exceeds 1 MB.", "details": {}}})(
                    scope, receive, send)
                return
            retry = _rate_limited(scope["path"], scope.get("client"))
            if retry is not None:
                await JSONResponse(status_code=429, headers={"Retry-After": str(retry)}, content={"error": {
                    "code": "RATE_LIMITED", "message": "Too many requests. Please slow down.",
                    "details": {"retry_after_seconds": retry}}})(scope, receive, send)
                return
        await self.inner(scope, receive, send)


class GuestWriteGuard:
    """FR-4.3: any write with a guest_* bearer is rejected (403) before routing or validation."""

    def __init__(self, app):
        self.inner = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] != "GET":
            from .domain.guest import bearer, write_rejection
            auth = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"authorization"), None)
            err = write_rejection(scope["method"], scope["path"], bearer(auth))
            if err is not None:
                await JSONResponse(status_code=err.status, content=err.body())(scope, receive, send)
                return
        await self.inner(scope, receive, send)


app.add_middleware(GuestWriteGuard)
app.add_middleware(LimitsMiddleware)

app.include_router(audit.router)
app.include_router(day2.router)
app.include_router(guest.router)
app.include_router(guest.ws_router)
app.include_router(web.router)
app.include_router(creator.router)
app.include_router(rbac.router)
app.include_router(api.router)
app.include_router(api.ws_router)
