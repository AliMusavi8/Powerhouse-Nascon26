"""Demo content for the mobile app. All ids are prefixed "demo-" so they never collide with grader ids.

Seeded on every reset: extra clubs in league-alpha-1, a round of fixtures (completed, live, upcoming)
driven through the real event log, a roster scenario for the club manager, and extra store products.
"""
from .db import J

LEAGUE = "league-alpha-1"
DEMO_CLUBS = [
    {"club_id": "demo-club-falcons", "name": "Falcons FC", "venue": "Falcon Park", "lat": 33.65, "lng": 73.02},
    {"club_id": "demo-club-lions", "name": "Lions SC", "venue": "Lions Den", "lat": 33.71, "lng": 73.09},
]
FIXTURES = [
    # (match_id, home, away, scheduled_at, venue, goals as list of scoring team ids, state)
    ("demo-m1", "club-alpha-1", "club-alpha-2", "2026-10-10T15:00:00Z", "Alpha Arena",
     ["club-alpha-1", "club-alpha-1", "club-alpha-2"], "completed"),
    ("demo-m2", "demo-club-falcons", "demo-club-lions", "2026-10-10T18:00:00Z", "Falcon Park",
     ["demo-club-lions"], "completed"),
    ("demo-m3", "club-alpha-1", "demo-club-falcons", "2026-10-14T15:00:00Z", "Alpha Arena",
     ["demo-club-falcons", "club-alpha-1"], "completed"),
    ("demo-m4", "club-alpha-2", "demo-club-lions", "2026-10-17T13:00:00Z", "City Ground",
     ["club-alpha-2"], "live"),
    ("demo-m5", "demo-club-lions", "club-alpha-1", "2026-10-21T15:00:00Z", "Lions Den", [], "upcoming"),
    ("demo-m6", "demo-club-falcons", "club-alpha-2", "2026-10-21T18:00:00Z", "Falcon Park", [], "upcoming"),
]
SQUAD_PLAYERS = {
    "club-alpha-1": [("player-alpha-1", "Ali Raza", "fw", "captain"), ("demo-p-a1-gk", "Hassan Ali", "gk", "starter"),
                     ("demo-p-a1-df", "Zain Abbas", "df", "vice_captain"), ("demo-p-a1-mf", "Saad Iqbal", "mf", "starter"),
                     ("demo-p-a1-sub", "Faisal Khan", "mf", "substitute")],
    "club-alpha-2": [("player-alpha-2", "Bilal Ahmed", "gk", "starter"), ("demo-p-a2-fw", "Omar Farooq", "fw", "captain"),
                     ("demo-p-a2-df", "Talha Aziz", "df", "starter")],
    "demo-club-falcons": [("demo-p-f-gk", "Asad Mehmood", "gk", "starter"), ("demo-p-f-fw", "Noman Riaz", "fw", "captain")],
    "demo-club-lions": [("demo-p-l-gk", "Danish Iqbal", "gk", "starter"), ("demo-p-l-fw", "Yasir Shah", "fw", "captain")],
}
PRODUCTS = [
    {"product_id": "demo-prod-scarf", "name": "Alpha United Scarf", "category": "accessories",
     "description": "Knitted supporters scarf.", "variants": [("demo-var-scarf-std", 150000, {"color": "Blue/Gold"}, 40)]},
    {"product_id": "demo-prod-cap", "name": "Training Cap", "category": "apparel",
     "description": "Adjustable cotton cap.",
     "variants": [("demo-var-cap-blue", 120000, {"color": "Blue"}, 25), ("demo-var-cap-white", 120000, {"color": "White"}, 0)]},
    {"product_id": "demo-prod-wallpaper", "name": "Matchday Wallpaper Pack", "category": "digital",
     "description": "Digital download, 10 HD wallpapers.", "variants": [("demo-var-wallpaper", 30000, {"format": "HD"}, 999)]},
]


def seed(cur) -> None:
    from .services.matches import _append  # local import: services depend on db helpers

    for c in DEMO_CLUBS:
        cur.execute("INSERT INTO clubs (club_id, tenant_id, league_id, name, profile) VALUES (%s,'tenant-alpha',%s,%s,%s)",
                    (c["club_id"], LEAGUE, c["name"], J({"home_venue": {"name": c["venue"], "lat": c["lat"], "lng": c["lng"]},
                                                         "socials": {}, "staff": [], "history": []})))
    for mid, home, away, when, venue, goals, state in FIXTURES:
        cur.execute("INSERT INTO matches (match_id, sport_id, league_id, home_team_id, away_team_id, scheduled_at, venue,"
                    " pinned_product_id) VALUES (%s,'football',%s,%s,%s,%s,%s,%s)",
                    (mid, LEAGUE, home, away, when, venue, "prod-jersey-001" if state == "live" else None))
        if state == "upcoming":
            continue
        _append(cur, {"event_id": f"{mid}-start", "match_id": mid, "type": "match_start", "payload": {}})
        for i, team in enumerate(goals):
            _append(cur, {"event_id": f"{mid}-g{i + 1}", "match_id": mid, "type": "score",
                          "payload": {"team_id": team, "event_type": "goal"}})
        if state == "completed":
            _append(cur, {"event_id": f"{mid}-end", "match_id": mid, "type": "match_end", "payload": {}})

    cur.execute("INSERT INTO roster_leagues (league_id, config) VALUES (%s, %s)", (LEAGUE, J({
        "league_id": LEAGUE, "tenant_id": "tenant-alpha", "sport_id": "football",
        "transfer_window": {"open": "2026-07-01", "close": "2026-12-31"},
        "max_squad_size": 25, "required_positions": {"gk": 1}})))
    names = {"club-alpha-1": "Alpha United", "club-alpha-2": "Alpha City"}
    names.update({c["club_id"]: c["name"] for c in DEMO_CLUBS})
    for club_id, players in SQUAD_PLAYERS.items():
        cur.execute("INSERT INTO squads (league_id, squad_id, club_id, tenant_id, name) VALUES (%s,%s,%s,'tenant-alpha',%s)",
                    (LEAGUE, club_id, club_id, names[club_id]))
        for pid, name, pos, role in players:
            if not pid.startswith("player-"):
                cur.execute("INSERT INTO players (player_id, tenant_id, club_id, name, profile) VALUES (%s,'tenant-alpha',%s,%s,%s)",
                            (pid, club_id, name, J({"position": pos, "role": role})))
            cur.execute("INSERT INTO registrations (league_id, player_id, name, position, squad_id, role, registration_type)"
                        " VALUES (%s,%s,%s,%s,%s,%s,'initial')", (LEAGUE, pid, name, pos, club_id, role))

    for p in PRODUCTS:
        cur.execute("INSERT INTO products (product_id, tenant_id, club_id, data) VALUES (%s,'tenant-alpha','club-alpha-1',%s)",
                    (p["product_id"], J({"name": p["name"], "category": p["category"], "description": p["description"]})))
        for vid, price, attrs, stock in p["variants"]:
            cur.execute("INSERT INTO variants (variant_id, product_id, price_minor, currency, stock, reserved, attributes)"
                        " VALUES (%s,%s,%s,'PKR',%s,0,%s)", (vid, p["product_id"], price, stock, J(attrs)))
