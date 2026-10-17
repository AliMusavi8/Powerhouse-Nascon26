import pytest

from app.domain import sync
from app.errors import ApiError


def act(aid, queued, type_="score_event", base=0):
    return {"action_id": aid, "type": type_, "queued_at": queued, "base_version": base, "payload": {}}


def test_envelope_validation():
    ok = {"device_id": "d1", "actions": [act("a1", "2026-10-17T11:00:00Z")]}
    assert len(sync.validate_envelope(ok)) == 1
    for bad in ({"device_id": "d|1", "actions": ok["actions"]}, {"device_id": "d", "actions": []},
                {"device_id": "d", "actions": [act("a", "2026-10-17 11:00")]},
                {"device_id": "d", "actions": [act("a", "2026-10-17T11:00:00Z", type_="x")]},
                {"device_id": "d", "actions": [act("a", "2026-10-17T11:00:00Z", base=-1)]},
                {"device_id": "d", "actions": [act("a", "2026-10-17T11:00:00Z")] * 2},
                {"device_id": "d", "actions": [act(f"a{i}", "2026-10-17T11:00:00Z") for i in range(101)]}):
        with pytest.raises(ApiError):
            sync.validate_envelope(bad)


def test_processing_order_is_stable():
    actions = [act("a", "2026-10-17T11:01:00Z"), act("b", "2026-10-17T11:00:00Z"), act("c", "2026-10-17T11:01:00Z")]
    assert sync.processing_order(actions) == [1, 0, 2]


def test_summary():
    rs = [sync.result("a", "applied", "appended", None, 1, 3), sync.result("b", "rejected", "server_wins", "X", 2, 3),
          sync.result("c", "duplicate", "skipped_duplicate", None, 3, 3)]
    assert sync.summarize(rs) == {"applied": 1, "rejected": 1, "duplicate": 1}
    assert rs[0]["signature"] is None and rs[1]["error_code"] == "X"
