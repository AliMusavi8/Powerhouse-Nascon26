"""NFR-1: a score event appended through /audit/v1/events reaches 25 concurrent WebSocket clients, p95 < 500 ms."""
import asyncio
import json
import os
import time
import uuid

import pytest
import requests

websockets = pytest.importorskip("websockets")
BASE = os.environ.get("API_BASE", "http://localhost:8080")
WS = BASE.replace("http", "ws", 1)
CLIENTS = 25


async def _client(ready: asyncio.Event, counter: list, fired: dict, latencies: list):
    async with websockets.connect(f"{WS}/ws/matches/match-m1") as ws:
        await ws.recv()  # subscribed
        counter.append(1)
        if len(counter) == CLIENTS:
            ready.set()
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if msg.get("type") == "match_updated" and "home" in msg:
                latencies.append(time.perf_counter() - fired["t"])
                return msg


async def _run():
    ready, counter, fired, latencies = asyncio.Event(), [], {}, []
    tasks = [asyncio.create_task(_client(ready, counter, fired, latencies)) for _ in range(CLIENTS)]
    await asyncio.wait_for(ready.wait(), timeout=10)
    fired["t"] = time.perf_counter()
    r = await asyncio.to_thread(requests.post, BASE + "/audit/v1/events", json={
        "event_id": "nfr1-" + uuid.uuid4().hex[:10], "match_id": "match-m1", "type": "score",
        "payload": {"team_id": "club-alpha-2", "event_type": "goal"}}, timeout=5)
    assert r.status_code == 201, r.text
    messages = await asyncio.gather(*tasks)
    return messages, sorted(latencies)


def test_score_broadcast_p95_under_500ms(fresh):
    messages, latencies = asyncio.run(_run())
    assert len(latencies) == CLIENTS
    p95 = latencies[int(0.95 * CLIENTS) - 1]
    assert p95 < 0.5, f"p95 {p95 * 1000:.0f} ms"
    assert all(m["away"]["score"] == 1 and m["home"]["score"] == 1 for m in messages)
