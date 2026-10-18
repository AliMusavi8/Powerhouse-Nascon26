"""Dynamic QR resolution, scan telemetry and SVG/PNG/PDF exports (spec 5.6)."""
import io

from .. import config, crypto, db
from ..domain import qr as rules
from ..errors import not_found
from . import matches


def qr_not_found(entity_id: str):
    return not_found("QR_NOT_FOUND", f"No dynamic QR mapping for {entity_id}.", entity_id=entity_id)


def _entity_type(cur, entity_id: str) -> str | None:
    for table, column, kind in (("matches", "match_id", "match"), ("clubs", "club_id", "club"),
                                ("players", "player_id", "player"), ("costream_sessions", "session_id", "costream")):
        cur.execute(f"SELECT 1 FROM {table} WHERE {column} = %s", (entity_id,))
        if cur.fetchone():
            return kind
    return None


def _status(cur, entity_type: str, entity_id: str) -> str:
    if entity_type == "match":
        log = matches.load_log(cur, entity_id)
        return log.status if log else "upcoming"
    if entity_type == "costream":
        cur.execute("SELECT state FROM costream_sessions WHERE session_id = %s", (entity_id,))
        row = cur.fetchone()
        return row["state"]["status"] if row else "active"
    return "active"


def _mapping(cur, entity_id: str, create: bool = True) -> dict:
    cur.execute("SELECT entity_id, entity_type, short_code, scan_count FROM qr_codes WHERE entity_id = %s",
                (entity_id,))
    row = cur.fetchone()
    if row:
        return row
    kind = _entity_type(cur, entity_id) if create else None
    if kind is None:
        raise qr_not_found(entity_id)
    cur.execute("INSERT INTO qr_codes (entity_id, entity_type, short_code) VALUES (%s,%s,%s) "
                "ON CONFLICT (entity_id) DO NOTHING", (entity_id, kind, rules.short_code(entity_id, config.DAY2_SALT)))
    cur.execute("SELECT entity_id, entity_type, short_code, scan_count FROM qr_codes WHERE entity_id = %s",
                (entity_id,))
    return cur.fetchone()


def _record_scan(cur, entity_id: str, user_agent: str | None) -> int:
    cur.execute("UPDATE qr_codes SET scan_count = scan_count + 1 WHERE entity_id = %s RETURNING scan_count",
                (entity_id,))
    count = cur.fetchone()["scan_count"]
    cur.execute("INSERT INTO qr_scan_stats (entity_id, device_family, bucket, count) VALUES (%s,%s,%s,1) "
                "ON CONFLICT (entity_id, device_family, bucket) DO UPDATE SET count = qr_scan_stats.count + 1",
                (entity_id, rules.device_family(user_agent), rules.bucket()))
    return count


def _view(cur, row: dict, scan_count: int) -> dict:
    entity_id, kind = row["entity_id"], row["entity_type"]
    status = _status(cur, kind, entity_id)
    short_url = f"{config.PUBLIC_BASE}/q/{row['short_code']}"
    route = rules.target_route(kind, entity_id, status)
    signature = crypto.sign_day2(entity_id, rules.sig_payload(entity_id, short_url, route))
    return rules.view(entity_id, kind, status, short_url, route, scan_count, config.PUBLIC_BASE, signature)


def resolve(entity_id: str, inspect: bool, user_agent: str | None = None) -> dict:
    with db.tx() as cur:
        row = _mapping(cur, entity_id)
        count = row["scan_count"] if inspect else _record_scan(cur, entity_id, user_agent)
        return _view(cur, row, count)


def scan_short_code(code: str, user_agent: str | None) -> dict:
    with db.tx() as cur:
        cur.execute("SELECT entity_id, entity_type, short_code, scan_count FROM qr_codes WHERE short_code = %s",
                    (code,))
        row = cur.fetchone()
        if row is None:
            raise qr_not_found(code)
        return _view(cur, row, _record_scan(cur, row["entity_id"], user_agent))


def export(entity_id: str, fmt: str) -> tuple[bytes, str]:
    import segno
    with db.tx() as cur:
        row = _mapping(cur, entity_id)
    short_url = f"{config.PUBLIC_BASE}/q/{row['short_code']}"
    code = segno.make(short_url, error="m")
    buf = io.BytesIO()
    if fmt == "svg":
        code.save(buf, kind="svg", scale=8, xmldecl=True, title=f"QR {entity_id}")
        return buf.getvalue(), "image/svg+xml"
    if fmt == "png":
        code.save(buf, kind="png", scale=10, border=4)
        return buf.getvalue(), "image/png"
    if fmt == "pdf":
        return _poster(entity_id, short_url, code), "application/pdf"
    raise qr_not_found(entity_id)


def _poster(entity_id: str, short_url: str, code) -> bytes:
    from fpdf import FPDF
    png = io.BytesIO()
    code.save(png, kind="png", scale=12, border=2)
    png.seek(0)
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 28)
    pdf.cell(0, 18, "Scan to watch live", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.image(png, x=45, y=40, w=120, h=120)
    pdf.set_y(170)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, entity_id, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 14)
    pdf.cell(0, 10, short_url, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "No app or account needed.", align="C")
    return bytes(pdf.output())


def total_scans() -> int:
    with db.tx() as cur:
        cur.execute("SELECT COALESCE(SUM(scan_count), 0) AS n FROM qr_codes")
        return int(cur.fetchone()["n"])
