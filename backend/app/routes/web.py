"""Guest Web Player pages (/web/*). One static shell; the script reads the page type and id from the URL."""
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from ..errors import not_found

router = APIRouter()
WEB = Path(__file__).resolve().parent.parent / "web"
STATIC = {"app.js": "text/javascript", "app.css": "text/css", "hls.min.js": "text/javascript",
          "board.js": "text/javascript", "board.css": "text/css"}
MATCH_VIEWS = ("live", "preview", "vod", "notice")


@lru_cache(maxsize=16)
def _read(name: str) -> bytes:
    return (WEB / name).read_bytes()


def _page() -> HTMLResponse:
    return HTMLResponse(_read("player.html"), headers={"Cache-Control": "no-store"})


@router.get("/web")
@router.get("/web/")
async def board_page():
    return HTMLResponse(_read("board.html"), headers={"Cache-Control": "no-store"})


@router.get("/web/static/{name}")
async def static(name: str):
    if name not in STATIC:
        raise not_found("NOT_FOUND", "No such file.")
    return Response(_read(name), media_type=STATIC[name], headers={"Cache-Control": "public, max-age=300"})


@router.get("/web/matches/{match_id}/{view}")
async def match_page(match_id: str, view: str):
    if view not in MATCH_VIEWS:
        raise not_found("NOT_FOUND", "No such page.")
    return _page()


@router.get("/web/costream/{session_id}")
async def costream_page(session_id: str):
    return _page()


@router.get("/web/players/{player_id}")
async def player_page(player_id: str):
    return _page()


@router.get("/web/clubs/{club_id}")
async def club_page(club_id: str):
    return _page()
