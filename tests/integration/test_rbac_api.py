import base64
import json
import time

import requests

A, D = 200, 403
ROLES = ["super_admin", "league_organizer", "club_manager", "player", "viewer"]

# (method, path template, target key or None) -> expected per role (spec 5.13 matrix)
MATRIX = [
    ("POST", "/audit/v1/rbac/tenants", None, [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/leagues/{}/fixtures", "own_league_id", [A, A, D, D, D]),
    ("POST", "/audit/v1/rbac/leagues/{}/fixtures", "other_league_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/leagues/{}/fixtures", "foreign_league_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/roster", "own_club_id", [A, D, A, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/roster", "other_club_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/roster", "foreign_club_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/products", "own_club_id", [A, D, A, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/products", "other_club_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/products", "foreign_club_id", [A, D, D, D, D]),
    ("PATCH", "/audit/v1/rbac/players/{}", "own_player_id", [A, D, A, A, D]),
    ("PATCH", "/audit/v1/rbac/players/{}", "other_player_id", [A, D, D, D, D]),
    ("PATCH", "/audit/v1/rbac/players/{}", "foreign_player_id", [A, D, D, D, D]),
    ("GET", "/audit/v1/rbac/clubs/{}", "own_club_id", [A, A, A, A, A]),
    ("GET", "/audit/v1/rbac/clubs/{}", "other_club_id", [A, A, A, A, A]),
    ("GET", "/audit/v1/rbac/clubs/{}", "foreign_club_id", [A, D, D, D, D]),
    ("GET", "/audit/v1/rbac/platform/config", None, [A, D, D, D, D]),
]


def _b64(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def test_full_matrix(fresh):
    api = fresh
    m = api.post("/audit/v1/rbac-matrix").json()
    tokens, ctx = m["tokens"], m["context"]
    for method, path, key, expected in MATRIX:
        url = path.format(ctx[key]) if key else path
        for role, exp in zip(ROLES, expected):
            r = api.s.request(method, api.base + url, json={},
                              headers={"Authorization": "Bearer " + tokens[role]}, timeout=10)
            assert r.status_code == exp, (method, url, role, r.status_code, r.text)
            if exp == D:
                assert r.json()["error"]["code"] == "FORBIDDEN"
            else:
                assert r.json() == {"authorized": True}


def test_token_attacks(fresh):
    api = fresh
    tok = api.post("/audit/v1/rbac-matrix").json()["tokens"]["super_admin"]
    P7 = "/audit/v1/rbac/platform/config"
    assert api.get(P7).status_code == 401 and api.get(P7).json()["error"]["code"] == "UNAUTHENTICATED"
    head, body, sig = tok.split(".")
    tampered = f"{head}.{body}.{sig[:-2]}{'AA' if sig[-2:] != 'AA' else 'BB'}"
    assert api.get(P7, headers={"Authorization": "Bearer " + tampered}).status_code == 401
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    none_tok = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."
    assert api.get(P7, headers={"Authorization": "Bearer " + none_tok}).status_code == 401
    forged = f"{head}.{_b64(dict(claims, role='super_admin', exp=int(time.time()) + 99999))}.{sig}"
    assert api.get(P7, headers={"Authorization": "Bearer " + forged}).status_code == 401
    assert api.get(P7, headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_rate_limit(api):
    s = requests.Session()
    first = s.get(api.base + "/api/v1/ping", timeout=5)
    codes = [first.status_code] + [s.get(api.base + "/api/v1/ping", timeout=5).status_code for _ in range(149)]
    assert first.json() == {"pong": True}
    assert codes.count(429) >= 40 and 500 not in codes
    r = s.get(api.base + "/api/v1/ping", timeout=5)
    assert r.status_code == 429 and "Retry-After" in r.headers and r.json()["error"]["code"] == "RATE_LIMITED"
    time.sleep(11)
    assert s.get(api.base + "/api/v1/ping", timeout=5).status_code == 200
    # /audit/v1/* is never rate limited
    assert all(s.get(api.base + "/health", timeout=5).status_code == 200 for _ in range(120))
