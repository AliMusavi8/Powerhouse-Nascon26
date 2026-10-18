"""Guest access (FR-4.2, FR-4.3, FR-4.4): read-only boundary for anonymous tokens and cart-merge rules.

Pure functions. The middleware in main.py and the cart-merge service both call `write_rejection()`, so the
server enforces exactly one rule: a guest_* bearer can never mutate state.
"""
from ..errors import ApiError, validation
from .validate import is_id, is_int

GUEST_PREFIX = "guest_"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Guest-scoped writes: creating a guest session and staging the local guest cart.
GUEST_ALLOWED = frozenset({("POST", "/api/v1/guest/session"), ("POST", "/api/v1/guest/cart")})


def is_guest_token(token) -> bool:
    return isinstance(token, str) and token.startswith(GUEST_PREFIX)


def bearer(authorization: str | None) -> str | None:
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


def guest_forbidden(token: str | None) -> ApiError:
    return ApiError(403, "GUEST_WRITE_FORBIDDEN", "Anonymous guest tokens cannot perform write mutations.",
                    {"guest_token": token})


def write_rejection(method: str, path: str, token: str | None) -> ApiError | None:
    """The 403 for a guest token attempting a state-changing request, else None."""
    if method.upper() not in WRITE_METHODS or not is_guest_token(token):
        return None
    if (method.upper(), path.rstrip("/")) in GUEST_ALLOWED:
        return None
    return guest_forbidden(token)


def validate_cart_merge(body: dict) -> dict:
    bad = []
    token = body.get("guest_token")
    if not isinstance(token, str) or not token.startswith(GUEST_PREFIX) or len(token) > 128:
        bad.append("guest_token")
    user = body.get("registered_user_id")
    if not is_id(user):
        bad.append("registered_user_id")
    cart = body.get("guest_cart")
    if not isinstance(cart, list) or not (1 <= len(cart) <= 10):
        bad.append("guest_cart")
    else:
        for item in cart:
            if (not isinstance(item, dict) or not is_id(item.get("variant_id"))
                    or not is_int(item.get("quantity")) or item["quantity"] < 1):
                bad.append("guest_cart")
                break
    twb = body.get("test_write_block", True)
    if twb is None:
        twb = True
    if not isinstance(twb, bool):
        bad.append("test_write_block")
    if bad:
        raise validation(bad)
    return {"guest_token": token, "registered_user_id": user, "test_write_block": twb,
            "guest_cart": [{"variant_id": i["variant_id"], "quantity": i["quantity"]} for i in cart]}


def combine(lines: list[dict]) -> dict[str, int]:
    """Sum quantities per variant, keeping first-seen order."""
    out: dict[str, int] = {}
    for line in lines:
        out[line["variant_id"]] = out.get(line["variant_id"], 0) + line["quantity"]
    return out


def merge(existing: dict[str, int], incoming: dict[str, int], stock: dict[str, int]) -> dict[str, int]:
    """Merged cart (quantities summed per variant). Raises 409 OUT_OF_STOCK when a variant exceeds stock."""
    merged = dict(existing)
    for variant_id, qty in incoming.items():
        total = merged.get(variant_id, 0) + qty
        if total > stock.get(variant_id, 0):
            raise ApiError(409, "OUT_OF_STOCK", f"Variant {variant_id} does not have enough stock.",
                           {"variant_id": variant_id, "requested": total, "available": stock.get(variant_id, 0)})
        merged[variant_id] = total
    return merged


def cart_view(user_id: str, quantities: dict[str, int], prices: dict[str, int]) -> dict:
    items = [{"variant_id": v, "quantity": q, "unit_price_minor": prices[v]} for v, q in quantities.items()]
    return {"user_id": user_id, "currency": "PKR", "total_items": sum(q for q in quantities.values()),
            "subtotal_minor": sum(i["quantity"] * i["unit_price_minor"] for i in items), "items": items}
