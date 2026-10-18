"""In-process pub/sub for WebSocket clients (live score, pinned product)."""
import asyncio
import threading

_loop: asyncio.AbstractEventLoop | None = None
_subscribers: dict[str, set[asyncio.Queue]] = {}
_lock = threading.Lock()


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe(topic: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    with _lock:
        _subscribers.setdefault(topic, set()).add(q)
    return q


def unsubscribe(topic: str, q: asyncio.Queue) -> None:
    with _lock:
        _subscribers.get(topic, set()).discard(q)


def publish(topic: str, message: dict) -> None:
    if _loop is None:
        return
    with _lock:
        queues = list(_subscribers.get(topic, ()))
    for q in queues:
        _loop.call_soon_threadsafe(_offer, q, message)


def _offer(q: asyncio.Queue, message: dict) -> None:
    if not q.full():
        q.put_nowait(message)


_connections = 0


def connection_opened() -> None:
    global _connections
    with _lock:
        _connections += 1


def connection_closed() -> None:
    global _connections
    with _lock:
        _connections = max(0, _connections - 1)


def connection_count() -> int:
    return _connections


def publish_match(match_id: str, snapshot: dict | None = None) -> None:
    """Live score push. The score travels in the message so clients update without refetching (NFR-1)."""
    message = {"type": "match_updated", "match_id": match_id}
    if snapshot:
        message.update({k: snapshot[k] for k in ("status", "version") if k in snapshot})
        for side in ("home", "away"):
            if side in snapshot:
                message[side] = {"team_id": snapshot[side]["team_id"], "score": snapshot[side]["score"]}
    publish("match:" + match_id, message)
