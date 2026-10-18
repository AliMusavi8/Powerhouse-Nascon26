"""Phase II autograder contract (/audit/v1/* Part II), short links (/q/*), metrics and the media hooks."""
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse, Response

from ..domain.metrics import CONTENT_TYPE
from ..http import read_object, respond

router = APIRouter()


@router.post("/audit/v1/stream/key")
async def stream_key(request: Request):
    from ..services import streams
    body = await read_object(request)
    status, result = await run_in_threadpool(streams.handle, body)
    return respond(status, result)


@router.post("/audit/v1/costream/session")
async def costream_session(request: Request):
    from ..services import costream
    body = await read_object(request)
    status, result = await run_in_threadpool(costream.handle, body)
    return respond(status, result)


@router.get("/audit/v1/qr/{entity_id}/export.{fmt}")
async def qr_export(entity_id: str, fmt: str):
    from ..services import qr
    content, media_type = await run_in_threadpool(qr.export, entity_id, fmt)
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'inline; filename="qr-{entity_id}.{fmt}"'})


@router.get("/audit/v1/qr/{entity_id}")
async def qr_resolve(request: Request, entity_id: str, inspect: str | None = None):
    from ..services import qr
    peek = (inspect or "").lower() in ("true", "1", "yes")
    if peek:
        hit = qr.cached(entity_id)
        if hit is not None:
            return respond(200, hit)
    return respond(200, await run_in_threadpool(qr.resolve, entity_id, peek, request.headers.get("user-agent")))


@router.get("/q/{short_code}")
async def short_link(request: Request, short_code: str, format: str | None = None):
    from ..services import qr
    view = await run_in_threadpool(qr.scan_short_code, short_code, request.headers.get("user-agent"))
    if format == "json":
        return respond(200, view)
    return RedirectResponse(view["target_route"], status_code=302, headers={"Cache-Control": "no-store"})


@router.post("/audit/v1/guest/cart-merge")
async def guest_cart_merge(request: Request):
    from ..services import guestcart
    body = await read_object(request)
    status, result = await run_in_threadpool(guestcart.merge, body)
    return respond(status, result)


@router.post("/audit/v1/moderation/test")
async def moderation_test(request: Request):
    from ..services import moderation
    body = await read_object(request)
    fast = moderation.fast_probe(body)
    if fast is not None:
        return respond(200, fast)
    return respond(200, await run_in_threadpool(moderation.probe, body))


@router.get("/metrics")
async def metrics():
    from ..services import observability
    text = await run_in_threadpool(observability.render)
    resp = Response(content=text.encode("utf-8"))
    resp.headers["content-type"] = CONTENT_TYPE
    return resp


@router.delete("/audit/v1/privacy/user/{user_id}")
async def privacy_erase(user_id: str):
    from ..services import observability
    return respond(200, await run_in_threadpool(observability.erase_user, user_id))


# ---------------------------------------------------------------- media server hooks (internal network)

@router.post("/internal/media/auth")
async def media_auth(request: Request):
    from ..services import streams
    body = await read_object(request, required=False)
    ok = await run_in_threadpool(streams.authorize_media, str(body.get("action", "")), str(body.get("path", "")),
                                 body.get("ip"))
    if ok:
        return Response(status_code=200)
    return JSONResponse(status_code=401, content={"error": {"code": "KEY_REVOKED",
                                                            "message": "Stream key is not active.", "details": {}}})


@router.post("/internal/media/recorded")
async def media_recorded(request: Request):
    from urllib.parse import parse_qs
    from ..services import vod
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode("utf-8", "replace")).items()}
    await run_in_threadpool(vod.recorded, form.get("path", ""), form.get("segment"))
    return Response(status_code=204)


@router.get("/internal/costream/{session_id}/layout")
async def costream_layout(session_id: str):
    from ..errors import not_found
    from ..services import costream
    layout = await run_in_threadpool(costream.layout, session_id)
    if layout is None:
        raise not_found("STREAM_NOT_FOUND", f"Co-stream {session_id} is not active.", session_id=session_id)
    return layout


@router.get("/api/v1/streams/key/{stream_key}")
async def stream_key_status(stream_key: str):
    from ..services import streams
    return await run_in_threadpool(streams.check_key, stream_key)
