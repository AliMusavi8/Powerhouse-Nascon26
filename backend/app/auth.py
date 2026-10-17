"""JWT issuing/verification and request authentication."""
import time

import jwt
from fastapi import Request

from . import config, db
from .domain.rbac import forbidden
from .errors import ApiError, not_found
from .passwords import verify_password

ALGORITHM = "HS256"


def unauthenticated(message: str = "Authentication is required.") -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", message)


def issue_token(user: dict) -> str:
    now = int(time.time())
    claims = {"sub": user["user_id"], "role": user["role"], "tenant_id": user.get("tenant_id"),
              "league_id": user.get("league_id"), "club_id": user.get("club_id"),
              "player_id": user.get("player_id"), "email": user.get("email"),
              "iat": now, "exp": now + config.JWT_TTL_SECONDS}
    return jwt.encode(claims, config.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != ALGORITHM:
            raise unauthenticated("Unsupported token algorithm.")
        claims = jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITHM],
                            options={"require": ["exp", "sub", "role"]})
    except jwt.ExpiredSignatureError:
        raise unauthenticated("The session has expired. Please sign in again.")
    except jwt.PyJWTError:
        raise unauthenticated("Invalid authentication token.")
    return claims


def principal(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise unauthenticated()
    return decode_token(token.strip())


def login(email, password) -> dict:
    if not isinstance(email, str) or not isinstance(password, str):
        raise ApiError(400, "VALIDATION_ERROR", "Email and password are required.", {"fields": ["email", "password"]})
    with db.tx() as cur:
        cur.execute("SELECT * FROM users WHERE lower(email) = lower(%s)", (email.strip(),))
        user = cur.fetchone()
    if user is None or not verify_password(password, user["password_hash"]):
        raise unauthenticated("Incorrect email or password.")
    return {"token": issue_token(user), "user": public_user(user)}


def public_user(user: dict) -> dict:
    return {k: user.get(k) for k in ("user_id", "email", "name", "role", "tenant_id", "league_id", "club_id",
                                     "player_id")}


def tokens_for_demo_users() -> dict:
    with db.tx() as cur:
        cur.execute("SELECT * FROM users")
        users = {u["role"]: u for u in cur.fetchall()}
    return {role: issue_token(users[role]) for role in
            ("super_admin", "league_organizer", "club_manager", "player", "viewer")}


# ---------------------------------------------------------------- authorization targets

def league_target(league_id: str) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT league_id, tenant_id FROM leagues WHERE league_id = %s", (league_id,))
        row = cur.fetchone()
    if row is None:
        raise not_found("LEAGUE_NOT_FOUND", f"League {league_id} not found.", league_id=league_id)
    return {"tenant_id": row["tenant_id"], "league_id": row["league_id"]}


def club_target(club_id: str) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT club_id, tenant_id, league_id FROM clubs WHERE club_id = %s", (club_id,))
        row = cur.fetchone()
    if row is None:
        raise not_found("CLUB_NOT_FOUND", f"Club {club_id} not found.", club_id=club_id)
    return {"tenant_id": row["tenant_id"], "club_id": row["club_id"]}


def player_target(player_id: str) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT player_id, tenant_id, club_id FROM players WHERE player_id = %s", (player_id,))
        row = cur.fetchone()
    if row is None:
        raise not_found("PLAYER_NOT_FOUND", f"Player {player_id} not found.", player_id=player_id)
    return {"tenant_id": row["tenant_id"], "player_id": row["player_id"], "player_club_id": row["club_id"]}


__all__ = ["forbidden"]
