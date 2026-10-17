"""Domain-event worker: consumes the Redis Stream written by the API (order and match status changes)."""
import json
import logging
import os
import time

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
log = logging.getLogger("worker")

STREAM = "domain-events"
GROUP = "workers"


def main() -> None:
    client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    while True:
        try:
            client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except redis.ResponseError:
            pass  # group already exists
        except redis.ConnectionError:
            time.sleep(1)
            continue
        break
    log.info("listening on stream %s", STREAM)
    while True:
        try:
            batches = client.xreadgroup(GROUP, "worker-1", {STREAM: ">"}, count=50, block=5000)
            for _, entries in batches or []:
                for entry_id, fields in entries:
                    event = json.loads(fields.get("event", "{}"))
                    log.info("event %s %s", event.get("type"), event.get("subject_id"))
                    client.xack(STREAM, GROUP, entry_id)
        except redis.ConnectionError:
            time.sleep(1)


if __name__ == "__main__":
    main()
