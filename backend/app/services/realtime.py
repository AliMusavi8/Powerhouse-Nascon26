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


def publish_match(match_id: str) -> None:
    publish("match:" + match_id, {"type": "match_updated", "match_id": match_id})
