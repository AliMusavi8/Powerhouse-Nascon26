"""VOD indexing (FR-3.2): MediaMTX records live/<key> to the shared volume; each finished segment is uploaded to
MinIO and indexed so the match /vod page can list it."""
import logging
import os
import threading
import uuid

from .. import db

log = logging.getLogger("nascon.vod")
BUCKET = os.environ.get("MINIO_BUCKET", "vod")


def _client():
    from minio import Minio
    return Minio(os.environ.get("MINIO_ENDPOINT", "minio:9000"), access_key=os.environ.get("MINIO_ACCESS_KEY", ""),
                 secret_key=os.environ.get("MINIO_SECRET_KEY", ""), secure=False)


def _upload(stream_key: str, segment: str) -> None:
    object_key = f"{stream_key}/{os.path.basename(segment)}"
    try:
        _client().fput_object(BUCKET, object_key, segment, content_type="video/mp4")
    except Exception as exc:  # storage outage must not affect the live stream
        log.warning("vod upload failed for %s: %s", segment, exc)
        return
    with db.tx() as cur:
        cur.execute("SELECT player_id FROM stream_keys WHERE stream_key = %s", (stream_key,))
        row = cur.fetchone()
        cur.execute("INSERT INTO vods (vod_id, stream_key, player_id, object_key) VALUES (%s,%s,%s,%s)",
                    ("vod-" + uuid.uuid4().hex[:12], stream_key, row["player_id"] if row else None, object_key))


def recorded(path: str, segment: str | None) -> None:
    if not path.startswith("live/") or not segment or not segment.startswith("/recordings/"):
        return
    threading.Thread(target=_upload, args=(path[len("live/"):], segment), daemon=True).start()


def list_for(stream_keys: list[str]) -> list[dict]:
    with db.tx() as cur:
        cur.execute("SELECT vod_id, stream_key, object_key, created_at FROM vods WHERE stream_key = ANY(%s) "
                    "ORDER BY created_at", (stream_keys,))
        return [dict(r, url=f"/vod/{r['object_key']}", created_at=r["created_at"].isoformat())
                for r in cur.fetchall()]
