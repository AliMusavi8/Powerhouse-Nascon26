"""Request helpers shared by all routers."""
import json

from fastapi import Request
from fastapi.responses import JSONResponse

from . import config
from .errors import ApiError, validation


async def read_json(request: Request, required: bool = True):
    raw = await request.body()
    if len(raw) > config.MAX_BODY_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.")
    if not raw.strip():
        if required:
            raise validation("body", "Request body is required.")
        return None
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise validation("body", "Malformed JSON.")


async def read_object(request: Request, required: bool = True) -> dict:
    body = await read_json(request, required)
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise validation("body", "Body must be a JSON object.")
    return body


def respond(status: int, body) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)
