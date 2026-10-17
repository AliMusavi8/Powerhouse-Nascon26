"""Checkout with concurrency-safe stock reservation, mock payment and signed PDF receipts."""
import base64
import threading

from psycopg.errors import UniqueViolation

from .. import crypto, db
from ..db import J
from ..domain import store as rules
from ..domain.validate import utc_now_iso
from ..errors import ApiError, conflict, not_found
from . import queue
from .pdf import receipt_pdf

_order_locks: dict[str, threading.Lock] = {}
_order_locks_guard = threading.Lock()
gateway = rules.MockGateway()


def _order_lock(order_id: str) -> threading.Lock:
    with _order_locks_guard:
        return _order_locks.setdefault(order_id, threading.Lock())


def checkout(body: dict) -> tuple[int, dict]:
    req = rules.validate_checkout(body)
    digest = crypto.body_hash(req)
    with _order_lock(req["order_id"]):
        return _checkout(req, digest)


def _checkout(req: dict, digest: str) -> tuple[int, dict]:
    order_id = req["order_id"]
    with db.tx() as cur:
        cur.execute("SELECT body_hash, response FROM orders WHERE order_id = %s", (order_id,))
        prior = cur.fetchone()
        if prior:
            if prior["body_hash"] == digest:
                return 200, prior["response"]
            raise conflict("DUPLICATE_ORDER_ID", f"Order id {order_id} was already used with a different body.",
                           order_id=order_id)
        ids = [i["variant_id"] for i in req["items"]]
        cur.execute("SELECT v.variant_id, v.price_minor, p.tenant_id FROM variants v "
                    "JOIN products p ON p.product_id = v.product_id WHERE v.variant_id = ANY(%s)", (ids,))
        rows = {r["variant_id"]: r for r in cur.fetchall()}
        for vid in ids:
            if vid not in rows:
                raise not_found("VARIANT_NOT_FOUND", f"Variant {vid} not found.", variant_id=vid)
        percent = 0
        if req["discount_code"] is not None:
            cur.execute("SELECT percent FROM discount_codes WHERE code = %s", (req["discount_code"],))
            code = cur.fetchone()
            if code is None:
                raise ApiError(400, "INVALID_DISCOUNT_CODE", "This discount code is not valid.",
                               {"discount_code": req["discount_code"]})
            percent = code["percent"]
    pricing = rules.price(req["items"], {v: r["price_minor"] for v, r in rows.items()}, percent)
    tenant_id = next(iter(rows.values()))["tenant_id"]

    _reserve(req["items"])
    token = req["payment"]["token"]
    try:
        auth_id = gateway.authorize(token, pricing["total_minor"])
        try:
            cap_id = gateway.capture(token, auth_id)
        except ApiError:
            gateway.void(auth_id)
            raise
    except ApiError:
        _release(req["items"])
        raise

    paid_at = utc_now_iso()
    payload = {"order_id": order_id, "customer_id": req["customer_id"], "items": pricing["items"],
               "subtotal_minor": pricing["subtotal_minor"], "discount_minor": pricing["discount_minor"],
               "total_minor": pricing["total_minor"], "currency": "PKR", "paid_at": paid_at}
    signature = crypto.sign(order_id, payload)
    pdf = receipt_pdf(payload, signature, _tenant_name(tenant_id))
    response = {
        "order_id": order_id, "status": "paid", "currency": "PKR", "items": pricing["items"],
        "subtotal_minor": pricing["subtotal_minor"], "discount_minor": pricing["discount_minor"],
        "total_minor": pricing["total_minor"],
        "payment": {"authorization_id": auth_id, "capture_id": cap_id, "state": "captured"},
        "receipt": {"payload": payload, "signature": signature, "pdf_base64": base64.b64encode(pdf).decode("ascii")},
    }
    try:
        with db.tx() as cur:
            for it in sorted(req["items"], key=lambda i: i["variant_id"]):
                cur.execute("UPDATE variants SET reserved = reserved - %s WHERE variant_id = %s",
                            (it["quantity"], it["variant_id"]))
            cur.execute("INSERT INTO orders (order_id, body_hash, customer_id, status, http_status, response, pdf)"
                        " VALUES (%s,%s,%s,'paid',201,%s,%s)",
                        (order_id, digest, req["customer_id"], J(response), pdf))
            cur.execute("INSERT INTO order_events (order_id, from_state, to_state) VALUES (%s,'pending','paid')",
                        (order_id,))
    except UniqueViolation:
        _release(req["items"])
        raise conflict("DUPLICATE_ORDER_ID", f"Order id {order_id} already exists.", order_id=order_id)
    queue.emit("order.status_changed", order_id, {"from": "pending", "to": "paid", "total_minor": pricing["total_minor"]})
    return 201, response


def _reserve(items: list[dict]) -> None:
    """All-or-nothing reservation: conditional decrements inside one transaction."""
    with db.tx() as cur:
        for it in sorted(items, key=lambda i: i["variant_id"]):
            cur.execute("UPDATE variants SET stock = stock - %s, reserved = reserved + %s "
                        "WHERE variant_id = %s AND stock >= %s RETURNING stock",
                        (it["quantity"], it["quantity"], it["variant_id"], it["quantity"]))
            if cur.fetchone() is None:
                raise conflict("OUT_OF_STOCK", f"Variant {it['variant_id']} has no stock left.",
                               variant_id=it["variant_id"])


def _release(items: list[dict]) -> None:
    with db.tx() as cur:
        for it in sorted(items, key=lambda i: i["variant_id"]):
            cur.execute("UPDATE variants SET stock = stock + %s, reserved = reserved - %s WHERE variant_id = %s",
                        (it["quantity"], it["quantity"], it["variant_id"]))


def _tenant_name(tenant_id: str) -> str:
    with db.tx() as cur:
        cur.execute("SELECT name FROM tenants WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
    return row["name"] if row else "Club Store"


def inventory(variant_id: str) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT variant_id, stock, reserved FROM variants WHERE variant_id = %s", (variant_id,))
        row = cur.fetchone()
    if row is None:
        raise not_found("VARIANT_NOT_FOUND", f"Variant {variant_id} not found.", variant_id=variant_id)
    return {"variant_id": row["variant_id"], "stock": row["stock"], "reserved": row["reserved"]}


def transition(order_id: str, target: str) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT status, response FROM orders WHERE order_id = %s FOR UPDATE", (order_id,))
        row = cur.fetchone()
        if row is None:
            raise not_found("ORDER_NOT_FOUND", f"Order {order_id} not found.", order_id=order_id)
        rules.check_transition(row["status"], target)
        cur.execute("UPDATE orders SET status = %s WHERE order_id = %s", (target, order_id))
        cur.execute("INSERT INTO order_events (order_id, from_state, to_state) VALUES (%s,%s,%s)",
                    (order_id, row["status"], target))
        if target in ("cancelled", "refunded"):
            for it in row["response"]["items"]:
                cur.execute("UPDATE variants SET stock = stock + %s WHERE variant_id = %s",
                            (it["quantity"], it["variant_id"]))
    queue.emit("order.status_changed", order_id, {"from": row["status"], "to": target})
    return {"order_id": order_id, "status": target}


def receipt(order_id: str) -> tuple[bytes, dict]:
    with db.tx() as cur:
        cur.execute("SELECT pdf, response, status FROM orders WHERE order_id = %s", (order_id,))
        row = cur.fetchone()
    if row is None:
        raise not_found("ORDER_NOT_FOUND", f"Order {order_id} not found.", order_id=order_id)
    return bytes(row["pdf"]), dict(row["response"], status=row["status"])
