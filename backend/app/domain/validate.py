"""Small validation helpers shared by the domain modules."""
import re
from datetime import date, datetime

from ..errors import validation

ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_id(v) -> bool:
    return isinstance(v, str) and bool(ID_RE.match(v))


def require_id(body: dict, field: str, nullable: bool = False):
    v = body.get(field)
    if v is None and nullable:
        return None
    if not is_id(v):
        raise validation(field)
    return v


def parse_date(v) -> date | None:
    if not isinstance(v, str) or not DATE_RE.match(v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def id_list(value, field: str, min_len: int, max_len: int) -> list[str]:
    if not isinstance(value, list) or not all(is_id(t) for t in value):
        raise validation(field)
    if len(set(value)) != len(value) or not (min_len <= len(value) <= max_len):
        raise validation(field)
    return value
