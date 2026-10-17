import pytest

from app.domain import store as rules
from app.errors import ApiError
from app.services.pdf import receipt_pdf


def body(**kw):
    b = {"order_id": "o1", "customer_id": "c1", "items": [{"variant_id": "v1", "quantity": 2}],
         "discount_code": None, "payment": {"token": "tok_success"}}
    b.update(kw)
    return b


def test_validate_checkout():
    assert rules.validate_checkout(body())["items"] == [{"variant_id": "v1", "quantity": 2}]
    for bad in (body(order_id="a|b"), body(customer_id=""), body(items=[]),
                body(items=[{"variant_id": "v1", "quantity": 11}]),
                body(items=[{"variant_id": "v1", "quantity": 1}, {"variant_id": "v1", "quantity": 1}]),
                body(discount_code=5), body(payment={})):
        with pytest.raises(ApiError) as e:
            rules.validate_checkout(bad)
        assert e.value.code == "VALIDATION_ERROR"


def test_pricing_and_discount_floor():
    p = rules.price([{"variant_id": "v1", "quantity": 3}], {"v1": 333}, 10)
    assert p["subtotal_minor"] == 999 and p["discount_minor"] == 99 and p["total_minor"] == 900
    assert rules.format_pkr(450000) == "PKR 4500.00" and rules.format_pkr(123456705) == "PKR 1234567.05"


def test_mock_gateway():
    g = rules.MockGateway()
    auth = g.authorize("tok_success", 100)
    assert auth.startswith("auth_") and g.capture("tok_success", auth).startswith("cap_")
    with pytest.raises(ApiError) as e:
        g.authorize("tok_declined", 100)
    assert e.value.status == 402 and e.value.code == "PAYMENT_DECLINED"
    auth = g.authorize("tok_capture_fail", 100)
    with pytest.raises(ApiError) as e:
        g.capture("tok_capture_fail", auth)
    assert e.value.code == "PAYMENT_CAPTURE_FAILED"
    g.void(auth)
    assert g.refund("cap_x").startswith("ref_")


def test_order_state_machine():
    rules.check_transition("paid", "packed")
    rules.check_transition("shipped", "delivered")
    with pytest.raises(ApiError) as e:
        rules.check_transition("delivered", "paid")
    assert e.value.code == "ILLEGAL_TRANSITION"


def test_receipt_pdf_contains_order_and_total():
    payload = {"order_id": "ord-001", "customer_id": "cust 'x' <script>", "paid_at": "2026-10-17T11:20:05Z",
               "items": [{"variant_id": "var-jersey-001-M", "quantity": 1, "unit_price_minor": 450000}],
               "subtotal_minor": 450000, "discount_minor": 0, "total_minor": 450000, "currency": "PKR"}
    pdf = receipt_pdf(payload, "ab" * 32)
    assert pdf.startswith(b"%PDF")
    pypdf = pytest.importorskip("pypdf")
    import io
    text = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "ord-001" in text and "PKR 4500.00" in text
