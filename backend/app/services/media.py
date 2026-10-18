"""MediaMTX control API client. Every call is best effort: a media outage never fails an API request."""
import json
import logging
import urllib.request

from .. import config

log = logging.getLogger("nascon.media")
CONN_KINDS = ("rtmpconns", "webrtcsessions", "rtspsessions", "srtconns")


def _call(method: str, path: str, timeout: float = 0.8):
    req = urllib.request.Request(config.MEDIAMTX_API + path, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body else None


def kick_path(path: str) -> int:
    """Disconnect every publisher/reader session on `path` (e.g. live/<key>). Returns sessions kicked."""
    kicked = 0
    for kind in CONN_KINDS:
        try:
            items = (_call("GET", f"/v3/{kind}/list") or {}).get("items", [])
        except Exception as exc:
            log.debug("media list %s failed: %s", kind, exc)
            continue
        for item in items:
            if item.get("path") == path:
                try:
                    _call("POST", f"/v3/{kind}/kick/{item['id']}")
                    kicked += 1
                except Exception as exc:
                    log.warning("media kick %s failed: %s", item.get("id"), exc)
    return kicked


def ready_paths() -> list[dict] | None:
    """Ready paths with byte counters, or None when MediaMTX is unreachable."""
    try:
        items = (_call("GET", "/v3/paths/list", timeout=0.5) or {}).get("items", [])
    except Exception:
        return None
    return [i for i in items if i.get("ready")]


def ping() -> bool:
    return ready_paths() is not None
