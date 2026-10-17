"""Server-side PDF receipts (fpdf2)."""
from fpdf import FPDF

from ..domain.store import format_pkr


def _safe(text) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


def receipt_pdf(payload: dict, signature: str, tenant_name: str = "Alpha Sports") -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, _safe(f"{tenant_name} - Official Store"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Payment receipt", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    for label, value in (("Order", payload["order_id"]), ("Customer", payload["customer_id"]),
                         ("Paid at", payload["paid_at"])):
        pdf.cell(0, 7, _safe(f"{label}: {value}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(90, 8, "Item", border=1)
    pdf.cell(25, 8, "Qty", border=1)
    pdf.cell(0, 8, "Unit price", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for it in payload["items"]:
        pdf.cell(90, 8, _safe(it["variant_id"]), border=1)
        pdf.cell(25, 8, str(it["quantity"]), border=1)
        pdf.cell(0, 8, format_pkr(it["unit_price_minor"]), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 7, f"Subtotal: {format_pkr(payload['subtotal_minor'])}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Discount: {format_pkr(payload['discount_minor'])}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, f"Total: {format_pkr(payload['total_minor'])}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.ln(6)
    pdf.multi_cell(0, 5, _safe(f"Signature (HMAC-SHA256): {signature}"))
    return bytes(pdf.output())
