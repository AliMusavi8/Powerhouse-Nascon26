"""Store rules (spec 5.12): checkout validation, pricing, mock payment gateway, order state machine."""
import secrets

from ..errors import ApiError, conflict, validation
from .validate import is_id, is_int

ORDER_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"packed", "cancelled", "refunded"},
    "packed": {"shipped", "cancelled", "refunded"},
    "shipped": {"delivered", "refunded"},
    "delivered": {"refunded"},
    "cancelled": set(),
    "refunded": set(),
}


def validate_checkout(body: dict) -> dict:
    bad = []
    if not is_id(body.get("order_id")):
        bad.append("order_id")
    cust = body.get("customer_id")
    if not isinstance(cust, str) or not (1 <= len(cust) <= 200):
        bad.append("customer_id")
    items = body.get("items")
    if not isinstance(items, list) or not (1 <= len(items) <= 10):
        bad.append("items")
    else:
        seen = set()
        for it in items:
            if (not isinstance(it, dict) or not is_id(it.get("variant_id")) or it["variant_id"] in seen
                    or not is_int(it.get("quantity")) or not (1 <= it["quantity"] <= 10)):
                bad.append("items")
                break
            seen.add(it["variant_id"])
    code = body.get("discount_code")
    if code is not None and not isinstance(code, str):
        bad.append("discount_code")
    pay = body.get("payment")
    if not isinstance(pay, dict) or not isinstance(pay.get("token"), str):
        bad.append("payment")
    if bad:
        raise validation(bad)
    return {"order_id": body["order_id"], "customer_id": cust,
            "items": [{"variant_id": i["variant_id"], "quantity": i["quantity"]} for i in items],
            "discount_code": code, "payment": {"token": pay["token"]}}


def price(items: list[dict], prices: dict[str, int], percent: int) -> dict:
    lines = [{"variant_id": i["variant_id"], "quantity": i["quantity"], "unit_price_minor": prices[i["variant_id"]]}
             for i in items]
    subtotal = sum(line["quantity"] * line["unit_price_minor"] for line in lines)
    discount = subtotal * percent // 100
    return {"items": lines, "subtotal_minor": subtotal, "discount_minor": discount, "total_minor": subtotal - discount}


def format_pkr(minor: int) -> str:
    return f"PKR {minor // 100}.{minor % 100:02d}"


class MockGateway:
    """Deterministic mock payment gateway driven by the payment token."""

    def authorize(self, token: str, amount: int) -> str:
        if token != "tok_success" and token != "tok_capture_fail":
            raise ApiError(402, "PAYMENT_DECLINED", "The payment was declined by the bank.", {"token": token})
        return "auth_" + secrets.token_hex(6)

    def capture(self, token: str, authorization_id: str) -> str:
        if token == "tok_capture_fail":
            raise ApiError(402, "PAYMENT_CAPTURE_FAILED", "The payment could not be captured.",
                           {"authorization_id": authorization_id})
        return "cap_" + secrets.token_hex(6)

    def void(self, authorization_id: str) -> None:
        return None

    def refund(self, capture_id: str) -> str:
        return "ref_" + secrets.token_hex(6)


def check_transition(current: str, target: str) -> None:
    if target not in ORDER_TRANSITIONS.get(current, set()):
        raise conflict("ILLEGAL_TRANSITION", f"Order cannot move from {current} to {target}.",
                       **{"from": current, "to": target})
