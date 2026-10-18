"""Notification delivery with bounded exponential retry and a dead-letter queue (FR-5.2)."""
import uuid

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 0.1


def backoff_schedule(attempts: int = MAX_ATTEMPTS, base: float = BASE_DELAY_SECONDS) -> list[float]:
    """Delay before each retry: base, 2*base, 4*base ... (attempts - 1 waits)."""
    return [base * (2 ** i) for i in range(max(0, attempts - 1))]


def deliver(send, event: dict, attempts: int = MAX_ATTEMPTS, sleep=None) -> tuple[bool, int, str | None]:
    """Try `send(event)` up to `attempts` times. Returns (delivered, attempts_used, last_error)."""
    delays = backoff_schedule(attempts)
    last_error = None
    for i in range(attempts):
        try:
            if event.get("simulate_dlq"):
                raise RuntimeError("simulated downstream failure")
            send(event)
            return True, i + 1, None
        except Exception as exc:  # any delivery failure is retried, then dead-lettered
            last_error = str(exc) or exc.__class__.__name__
            if i < len(delays) and sleep is not None:
                sleep(delays[i])
    return False, attempts, last_error


def dead_letter(event_type: str, target: str, payload: dict, attempts: int, last_error: str, failed_at: str) -> dict:
    return {"event_id": "evt-" + uuid.uuid4().hex[:16], "type": event_type, "target": target, "payload": payload,
            "attempts": attempts, "last_error": last_error, "failed_at": failed_at}


def public(row: dict) -> dict:
    return {"event_id": row["event_id"], "type": row["type"], "target": row["target"], "attempts": row["attempts"],
            "last_error": row["last_error"], "failed_at": row["failed_at"]}
