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
from .routes import api, audit, rbac

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


# ---------------------------------------------------------------- body size limit

@app.middleware("http")
async def _body_limit(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > config.MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"error": {
            "code": "PAYLOAD_TOO_LARGE", "message": "Request body exceeds 1 MB.", "details": {}}})
    return await call_next(request)


# ---------------------------------------------------------------- rate limit (/api/v1/* only)

_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/v1/"):
        now = time.monotonic()
        window = config.RATE_LIMIT_WINDOW_SECONDS
        with _hits_lock:
            q = _hits.setdefault(_client_ip(request), deque())
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= config.RATE_LIMIT_REQUESTS:
                retry = max(1, int(window - (now - q[0])) + 1)
                return JSONResponse(status_code=429, headers={"Retry-After": str(retry)}, content={"error": {
                    "code": "RATE_LIMITED", "message": "Too many requests. Please slow down.",
                    "details": {"retry_after_seconds": retry}}})
            q.append(now)
    return await call_next(request)


app.include_router(audit.router)
app.include_router(rbac.router)
app.include_router(api.router)
app.include_router(api.ws_router)
