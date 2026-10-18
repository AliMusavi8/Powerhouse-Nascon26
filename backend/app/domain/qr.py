"""Dynamic QR deep-links (FR-4.1, spec 5.6): stable short codes, live target routes, privacy-safe telemetry."""
import base64
import hashlib
import hmac
from datetime import datetime, timezone

MATCH_ROUTES = {"upcoming": "preview", "in_progress": "live", "completed": "vod"}
NOTICE_STATES = ("postponed", "cancelled", "abandoned")
MOBILE_MARKERS = ("mobi", "android", "iphone", "ipad", "ipod", "windows phone", "blackberry", "opera mini")


def target_route(entity_type: str, entity_id: str, status: str | None) -> str:
    if entity_type == "match":
        if status in MATCH_ROUTES:
            return f"/web/matches/{entity_id}/{MATCH_ROUTES[status]}"
        return f"/web/matches/{entity_id}/notice?state={status}"
    if entity_type == "player":
        return f"/web/players/{entity_id}"
    if entity_type == "club":
        return f"/web/clubs/{entity_id}"
    return f"/web/costream/{entity_id}"


def short_code(entity_id: str, salt: str) -> str:
    digest = hmac.new((salt or "unset").encode("utf-8"), entity_id.encode("utf-8"), hashlib.sha256).digest()
    return base64.b32encode(digest).decode("ascii").lower()[:8]


def device_family(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    return "mobile" if any(m in ua for m in MOBILE_MARKERS) else "desktop"


def bucket(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:00Z")


def sig_payload(entity_id: str, short_url: str, route: str) -> dict:
    return {"entity_id": entity_id, "short_url": short_url, "target_route": route}


def view(entity_id: str, entity_type: str, status: str, short_url: str, route: str, scan_count: int,
         public_base: str, signature: str) -> dict:
    base = f"{public_base}/audit/v1/qr/{entity_id}/export"
    return {"entity_id": entity_id, "entity_type": entity_type, "entity_status": status, "short_url": short_url,
            "target_route": route, "deep_link_uri": f"nascon://entity/{entity_id}", "scan_count": scan_count,
            "export_formats": {"svg": base + ".svg", "png": base + ".png", "pdf": base + ".pdf"},
            "signature": signature}
