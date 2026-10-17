import base64
import io
import threading

import requests

from app.crypto import sign


def order(oid, variant="var-jersey-001-M", qty=1, token="tok_success", code=None, customer="cust-001"):
    return {"order_id": oid, "customer_id": customer, "items": [{"variant_id": variant, "quantity": qty}],
            "discount_code": code, "payment": {"token": token}}


def test_twenty_concurrent_buyers_one_unit(api):
    api.reset(stock={"var-jersey-001-M": 1})
    barrier = threading.Barrier(20)
    codes = []

    def buy(i):
        s = requests.Session()
        barrier.wait()
        r = s.post(api.base + "/audit/v1/checkout", json=order(f"ord-c{i}"), timeout=15)
        codes.append(r.status_code)

    threads = [threading.Thread(target=buy, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [201] + [409] * 19
    assert api.get("/audit/v1/inventory/var-jersey-001-M").json() == {
        "variant_id": "var-jersey-001-M", "stock": 0, "reserved": 0}


def test_checkout_receipt_and_rules(fresh):
    api = fresh
    r = api.post("/audit/v1/checkout", order("ord-001"))
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["status"] == "paid" and j["total_minor"] == 450000 and j["payment"]["state"] == "captured"
    assert j["receipt"]["signature"] == sign("ord-001", j["receipt"]["payload"], "demo-salt")
    pdf = base64.b64decode(j["receipt"]["pdf_base64"])
    assert pdf.startswith(b"%PDF")
    try:
        from pypdf import PdfReader
        text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
        assert "ord-001" in text and "PKR 4500.00" in text
    except ImportError:
        pass
    assert api.post("/audit/v1/checkout", order("ord-001")).status_code == 200
    assert api.post("/audit/v1/checkout", order("ord-001", qty=2)).json()["error"]["code"] == "DUPLICATE_ORDER_ID"
    assert api.post("/audit/v1/checkout", order("ord-002")).json()["error"]["code"] == "OUT_OF_STOCK"
    assert api.post("/audit/v1/checkout", order("ord-003", variant="nope")).json()["error"]["code"] == \
        "VARIANT_NOT_FOUND"
    assert api.post("/audit/v1/checkout", order("ord-003", variant="var-jersey-001-L", code="BOGUS")).json()[
        "error"]["code"] == "INVALID_DISCOUNT_CODE"
    r = api.post("/audit/v1/checkout", order("ord-004", variant="var-jersey-001-L", qty=2, code="WELCOME10"))
    assert r.status_code == 201 and r.json()["discount_minor"] == 90000 and r.json()["total_minor"] == 810000
    r = api.post("/audit/v1/checkout", order("ord-005", variant="var-jersey-001-L", token="tok_declined"))
    assert r.status_code == 402 and r.json()["error"]["code"] == "PAYMENT_DECLINED"
    r = api.post("/audit/v1/checkout", order("ord-006", variant="var-jersey-001-L", token="tok_capture_fail"))
    assert r.status_code == 402 and r.json()["error"]["code"] == "PAYMENT_CAPTURE_FAILED"
    assert api.get("/audit/v1/inventory/var-jersey-001-L").json() == {
        "variant_id": "var-jersey-001-L", "stock": 3, "reserved": 0}
    weird = order("ord-007", variant="var-jersey-001-L", customer="o'brien \"<script>alert(1)</script>")
    r = api.post("/audit/v1/checkout", weird)
    assert r.status_code == 201 and r.json()["receipt"]["payload"]["customer_id"] == weird["customer_id"]
    assert api.post("/audit/v1/checkout", dict(order("ord-008"), items=[])).status_code == 400
    assert api.get("/audit/v1/inventory/nope").status_code == 404
