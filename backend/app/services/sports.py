"""Sport registry (POST /audit/v1/sports)."""
from .. import db
from ..db import J
from ..domain.sports import validate_sport
from ..errors import conflict


def create(body: dict) -> dict:
    config = validate_sport(body)
    with db.tx() as cur:
        db.lock(cur, "sport:" + config["sport_id"])
        cur.execute("SELECT 1 FROM sports WHERE sport_id = %s", (config["sport_id"],))
        if cur.fetchone():
            raise conflict("SPORT_EXISTS", f"Sport {config['sport_id']} already exists.", sport_id=config["sport_id"])
        cur.execute("INSERT INTO sports (sport_id, config) VALUES (%s, %s)", (config["sport_id"], J(config)))
    return {"sport_id": config["sport_id"], "status": "created", "config": config}


def list_all() -> list[dict]:
    with db.tx() as cur:
        cur.execute("SELECT config FROM sports ORDER BY created_at, sport_id")
        return [r["config"] for r in cur.fetchall()]
