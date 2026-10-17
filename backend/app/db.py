"""PostgreSQL connection pool and transaction helper."""
import time
from contextlib import contextmanager
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import config

_pool: ConnectionPool | None = None

TABLES = [
    "meta", "tenants", "sports", "leagues", "clubs", "players", "users", "matches", "events",
    "roster_leagues", "squads", "registrations", "roster_live_matches", "roster_audit",
    "roster_requests", "products", "variants", "discount_codes", "orders", "order_events",
    "sync_actions",
]


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(config.DATABASE_URL, min_size=2, max_size=30, open=True,
                               kwargs={"row_factory": dict_row, "autocommit": False})
    return _pool


@contextmanager
def tx():
    """Yield a cursor inside one transaction; commit on success, roll back on error."""
    with pool().connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                yield cur


def wait_for_db(timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            with tx() as cur:
                cur.execute("SELECT 1")
            return
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(1)


def create_schema() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    with tx() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(4242)")
        cur.execute(sql)


def lock(cur, key: str) -> None:
    """Transaction-scoped advisory lock on an arbitrary string key."""
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))


def ping() -> bool:
    try:
        with tx() as cur:
            cur.execute("SELECT value FROM meta WHERE key = 'seeded'")
            return cur.fetchone() is not None
    except Exception:
        return False


J = Jsonb
