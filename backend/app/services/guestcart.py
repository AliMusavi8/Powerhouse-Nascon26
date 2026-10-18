"""Guest sessions, staged guest carts and the atomic guest → member cart merge (spec 5.7)."""
import secrets

from .. import config, crypto, db
from ..db import J
from ..domain import guest as rules
from ..errors import not_found


def _user_exists(cur, user_id: str) -> bool:
    cur.execute("SELECT 1 FROM players WHERE player_id = %s UNION ALL SELECT 1 FROM users WHERE user_id = %s",
                (user_id, user_id))
    return cur.fetchone() is not None


def _variants(cur, ids: list[str]) -> dict[str, dict]:
    cur.execute("SELECT variant_id, price_minor, stock FROM variants WHERE variant_id = ANY(%s)", (ids,))
    return {r["variant_id"]: r for r in cur.fetchall()}


def _cart(cur, user_id: str) -> dict[str, int]:
    cur.execute("SELECT variant_id, quantity FROM carts WHERE user_id = %s ORDER BY ord", (user_id,))
    return {r["variant_id"]: r["quantity"] for r in cur.fetchall()}


def _view(cur, user_id: str) -> dict:
    quantities = _cart(cur, user_id)
    prices = {v: r["price_minor"] for v, r in _variants(cur, list(quantities)).items()}
    return rules.cart_view(user_id, quantities, prices)


def merge(body: dict) -> tuple[int, dict]:
    req = rules.validate_cart_merge(body)
    token, user = req["guest_token"], req["registered_user_id"]
    incoming = rules.combine(req["guest_cart"])
    digest = crypto.body_hash({"registered_user_id": user, "guest_cart": req["guest_cart"]})
    rejection = rules.write_rejection("POST", "/api/v1/chat", token)
    rejection_code = rejection.status if rejection else 403
    with db.tx() as cur:
        if not _user_exists(cur, user):
            raise not_found("PLAYER_NOT_FOUND", f"User {user} not found.", registered_user_id=user)
        variants = _variants(cur, list(incoming))
        for vid in incoming:
            if vid not in variants:
                raise not_found("VARIANT_NOT_FOUND", f"Variant {vid} not found.", variant_id=vid)
        db.lock(cur, "guestmerge:" + token)
        db.lock(cur, "cart:" + user)
        cur.execute("SELECT merged_user_id, merged_hash FROM guest_tokens WHERE guest_token = %s FOR UPDATE",
                    (token,))
        row = cur.fetchone()
        if row and row["merged_user_id"] is not None:
            if row["merged_user_id"] != user or row["merged_hash"] != digest:
                raise rules_conflict(token)
            return 200, _response(req, rejection_code, _view(cur, user))
        merged = rules.merge(_cart(cur, user), incoming, {v: r["stock"] for v, r in variants.items()})
        for vid, qty in merged.items():
            cur.execute("INSERT INTO carts (user_id, variant_id, quantity) VALUES (%s,%s,%s) "
                        "ON CONFLICT (user_id, variant_id) DO UPDATE SET quantity = EXCLUDED.quantity",
                        (user, vid, qty))
        cur.execute("INSERT INTO guest_tokens (guest_token, merged_user_id, merged_hash, cart) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (guest_token) DO UPDATE SET merged_user_id = EXCLUDED.merged_user_id, "
                    "merged_hash = EXCLUDED.merged_hash, cart = '[]'", (token, user, digest, J([])))
        return 200, _response(req, rejection_code, _view(cur, user))


def rules_conflict(token: str):
    from ..errors import conflict
    return conflict("GUEST_TOKEN_ALREADY_MERGED", "This guest token has already been merged into an account.",
                    guest_token=token)


def _response(req: dict, rejection_code: int, cart: dict) -> dict:
    token = req["guest_token"]
    signature = crypto.sign_day2(token, {"cart_merged": True, "guest_token": token,
                                         "registered_user_id": req["registered_user_id"],
                                         "total_items": cart["total_items"], "write_rejection_code": rejection_code})
    return {"guest_token": token, "write_block_verified": req["test_write_block"],
            "write_rejection_code": rejection_code, "cart_merged": True, "active_cart": cart, "signature": signature}


# ---------------------------------------------------------------- guest sessions and staged carts (web player)

def new_session() -> dict:
    token = "guest_anon_tok_" + secrets.token_hex(6)
    with db.tx() as cur:
        cur.execute("INSERT INTO guest_tokens (guest_token, expires_at) VALUES "
                    "(%s, now() + make_interval(secs => %s)) RETURNING expires_at",
                    (token, config.GUEST_TOKEN_TTL_SECONDS))
        expires = cur.fetchone()["expires_at"]
    return {"guest_token": token, "role": "guest", "scopes": ["playback", "scores", "cart_stage"],
            "expires_at": expires.isoformat().replace("+00:00", "Z")}


def stage(token: str | None, body: dict) -> dict:
    from ..errors import ApiError, validation
    if not rules.is_guest_token(token):
        raise ApiError(401, "UNAUTHENTICATED", "A guest token is required.")
    vid, qty = body.get("variant_id"), body.get("quantity", 1)
    if not isinstance(vid, str) or not isinstance(qty, int) or isinstance(qty, bool) or not (1 <= qty <= 10):
        raise validation(["variant_id", "quantity"])
    with db.tx() as cur:
        if vid not in _variants(cur, [vid]):
            raise not_found("VARIANT_NOT_FOUND", f"Variant {vid} not found.", variant_id=vid)
        db.lock(cur, "guestmerge:" + token)
        cur.execute("SELECT cart, merged_user_id FROM guest_tokens WHERE guest_token = %s", (token,))
        row = cur.fetchone()
        if row and row["merged_user_id"]:
            raise rules_conflict(token)
        cart = rules.combine((row["cart"] if row else []) + [{"variant_id": vid, "quantity": qty}])
        lines = [{"variant_id": v, "quantity": q} for v, q in cart.items()]
        cur.execute("INSERT INTO guest_tokens (guest_token, cart) VALUES (%s,%s) "
                    "ON CONFLICT (guest_token) DO UPDATE SET cart = EXCLUDED.cart", (token, J(lines)))
    return {"guest_token": token, "items": lines, "count": sum(cart.values())}
