"""Demo content for the mobile app, loaded from seed/demo.json. All ids are prefixed "demo-" so they never
collide with grader ids.

Seeded on every reset: extra clubs in a tenant league, fixtures (completed, live, upcoming) driven through
the real event log, a roster scenario for the club manager, and extra store products.
"""
import json
from functools import lru_cache
from pathlib import Path

from .db import J


@lru_cache(maxsize=1)
def demo_data() -> dict:
    return json.loads((Path(__file__).parent / "seed" / "demo.json").read_text(encoding="utf-8"))


def seed(cur) -> None:
    from .services.matches import _append  # local import: services depend on db helpers

    d = demo_data()
    league, sport = d["league_id"], d["sport_id"]
    for c in d["clubs"]:
        cur.execute("INSERT INTO clubs (club_id, tenant_id, league_id, name, profile) VALUES (%s,'tenant-alpha',%s,%s,%s)",
                    (c["club_id"], league, c["name"], J({"home_venue": {"name": c["venue"], "lat": c["lat"], "lng": c["lng"]},
                                                         "socials": {}, "staff": [], "history": []})))
    for f in d["fixtures"]:
        mid = f["match_id"]
        cur.execute("INSERT INTO matches (match_id, sport_id, league_id, home_team_id, away_team_id, scheduled_at, venue,"
                    " pinned_product_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (mid, sport, league, f["home"], f["away"], f["scheduled_at"], f["venue"],
                     "prod-jersey-001" if f["state"] == "live" else None))
        if f["state"] == "upcoming":
            continue
        _append(cur, {"event_id": f"{mid}-start", "match_id": mid, "type": "match_start", "payload": {}})
        for i, team in enumerate(f["goals"]):
            _append(cur, {"event_id": f"{mid}-g{i + 1}", "match_id": mid, "type": "score",
                          "payload": {"team_id": team, "event_type": d["score_event"]}})
        if f["state"] == "completed":
            _append(cur, {"event_id": f"{mid}-end", "match_id": mid, "type": "match_end", "payload": {}})

    cur.execute("INSERT INTO roster_leagues (league_id, config) VALUES (%s, %s)", (league, J({
        "league_id": league, "tenant_id": "tenant-alpha", "sport_id": sport,
        "transfer_window": {"open": "2026-07-01", "close": "2026-12-31"},
        "max_squad_size": 25, "required_positions": {"gk": 1}})))
    cur.execute("SELECT club_id, name FROM clubs")
    names = {r["club_id"]: r["name"] for r in cur.fetchall()}
    for club_id, players in d["squads"].items():
        cur.execute("INSERT INTO squads (league_id, squad_id, club_id, tenant_id, name) VALUES (%s,%s,%s,'tenant-alpha',%s)",
                    (league, club_id, club_id, names[club_id]))
        for p in players:
            if not p["player_id"].startswith("player-"):
                cur.execute("INSERT INTO players (player_id, tenant_id, club_id, name, profile) VALUES (%s,'tenant-alpha',%s,%s,%s)",
                            (p["player_id"], club_id, p["name"], J({"position": p["position"], "role": p["role"]})))
            cur.execute("INSERT INTO registrations (league_id, player_id, name, position, squad_id, role, registration_type)"
                        " VALUES (%s,%s,%s,%s,%s,%s,'initial')",
                        (league, p["player_id"], p["name"], p["position"], club_id, p["role"]))

    for p in d["products"]:
        cur.execute("INSERT INTO products (product_id, tenant_id, club_id, data) VALUES (%s,'tenant-alpha','club-alpha-1',%s)",
                    (p["product_id"], J({"name": p["name"], "category": p["category"], "description": p["description"]})))
        for v in p["variants"]:
            cur.execute("INSERT INTO variants (variant_id, product_id, price_minor, currency, stock, reserved, attributes)"
                        " VALUES (%s,%s,%s,'PKR',%s,0,%s)",
                        (v["variant_id"], p["product_id"], v["price_minor"], v["stock"], J(v["attributes"])))
