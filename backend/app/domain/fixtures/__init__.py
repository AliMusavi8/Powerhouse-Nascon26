"""Fixture generation dispatcher (POST /audit/v1/fixtures). Pure computation, nothing is stored."""
from ...errors import validation
from ..validate import id_list
from . import elimination, round_robin, swiss

LIMITS = {
    "round_robin": (2, 40, round_robin.generate),
    "swiss": (2, 64, swiss.generate),
    "single_elim": (2, 128, elimination.single_elim),
    "double_elim": (3, 128, elimination.double_elim),
}


def generate(body: dict) -> dict:
    fmt = body.get("format")
    if fmt not in LIMITS:
        raise validation("format")
    lo, hi, fn = LIMITS[fmt]
    teams = id_list(body.get("teams"), "teams", lo, hi)
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise validation("params")
    return fn(teams, params)
