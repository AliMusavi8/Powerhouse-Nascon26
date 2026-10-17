"""Baseline data (spec 5.5). Used on first boot and by POST /audit/v1/reset."""
import json
from functools import lru_cache
from pathlib import Path

from . import db
from .db import J
from .passwords import hash_password

SEED_DIR = Path(__file__).parent / "seed"
DEFAULT_STOCK = {"var-jersey-001-M": 1, "var-jersey-001-L": 5}


@lru_cache(maxsize=1)
def sports_seed() -> list[dict]:
    return json.loads((SEED_DIR / "sports.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def baseline() -> dict:
    return json.loads((SEED_DIR / "baseline.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _demo_password_hash() -> str:
    return hash_password(baseline()["demo_password"])


def reset(seed: int = 42, stock: dict | None = None) -> dict:
    stock_map = dict(DEFAULT_STOCK)
    if stock:
        stock_map.update(stock)
    data = baseline()
    with db.tx() as cur:
        db.lock(cur, "global-reset")
        cur.execute("TRUNCATE " + ", ".join(db.TABLES) + " RESTART IDENTITY")
        for sport in sports_seed():
            cur.execute("INSERT INTO sports (sport_id, config) VALUES (%s, %s)", (sport["sport_id"], J(sport)))
        for t in data["tenants"]:
            cur.execute("INSERT INTO tenants (tenant_id, name, branding) VALUES (%s, %s, %s)",
                        (t["tenant_id"], t["name"], J(t["branding"])))
        for lg in data["leagues"]:
            cur.execute("INSERT INTO leagues (league_id, tenant_id, sport_id, name, config) VALUES (%s,%s,%s,%s,%s)",
                        (lg["league_id"], lg["tenant_id"], lg["sport_id"], lg["name"], J({})))
        for c in data["clubs"]:
            cur.execute("INSERT INTO clubs (club_id, tenant_id, league_id, name, profile) VALUES (%s,%s,%s,%s,%s)",
                        (c["club_id"], c["tenant_id"], c["league_id"], c["name"], J(c["profile"])))
        for p in data["players"]:
            cur.execute("INSERT INTO players (player_id, tenant_id, club_id, name, profile) VALUES (%s,%s,%s,%s,%s)",
                        (p["player_id"], p["tenant_id"], p["club_id"], p["name"], J(p["profile"])))
        for prod in data["products"]:
            cur.execute("INSERT INTO products (product_id, tenant_id, club_id, data) VALUES (%s,%s,%s,%s)",
                        (prod["product_id"], prod["tenant_id"], prod["club_id"], J(prod["data"])))
            for v in prod["variants"]:
                cur.execute(
                    "INSERT INTO variants (variant_id, product_id, price_minor, currency, stock, reserved, attributes)"
                    " VALUES (%s,%s,%s,'PKR',%s,0,%s)",
                    (v["variant_id"], prod["product_id"], v["price_minor"], int(stock_map.get(v["variant_id"], 0)),
                     J(v["attributes"])))
        for d in data["discount_codes"]:
            cur.execute("INSERT INTO discount_codes (code, percent) VALUES (%s, %s)", (d["code"], d["percent"]))
        for u in data["users"]:
            cur.execute(
                "INSERT INTO users (user_id, email, password_hash, name, role, tenant_id, league_id, club_id, player_id)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (u["user_id"], u["email"], _demo_password_hash(), u["name"], u["role"], u.get("tenant_id"),
                 u.get("league_id"), u.get("club_id"), u.get("player_id")))
        from . import demo  # demo content for the mobile app (ids prefixed "demo-")
        demo.seed(cur)
        cur.execute("INSERT INTO meta (key, value) VALUES ('seed', %s)", (J(seed),))
        cur.execute("INSERT INTO meta (key, value) VALUES ('seeded', %s)", (J(True),))
    return {
        "status": "reset_complete",
        "seed": seed,
        "sports": [s["sport_id"] for s in sports_seed()],
        "tenants": [t["tenant_id"] for t in data["tenants"]],
        "stock": stock_map,
    }


def current_seed(cur) -> int:
    cur.execute("SELECT value FROM meta WHERE key = 'seed'")
    row = cur.fetchone()
    return int(row["value"]) if row else 42
