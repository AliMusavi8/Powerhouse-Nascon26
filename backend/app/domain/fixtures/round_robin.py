"""Round-robin scheduling with the circle method (spec 5.7-A)."""
from ...errors import validation
from ..validate import is_int


def _balanced_orientation(teams: list[str]) -> set[tuple[str, str]]:
    """Orient every pair of K_n so each team's |home - away| <= 1.

    An Euler circuit of a graph with all-even degrees gives in-degree == out-degree. For an even
    team count the degrees are odd, so a dummy perfect matching is added first and dropped after.
    """
    n = len(teams)
    adj: dict[int, set[int]] = {i: {j for j in range(n) if j != i} for i in range(n)}
    dummy: set[frozenset] = set()
    if n % 2 == 0:
        for i in range(0, n, 2):
            dummy.add(frozenset((i, i + 1)))
    multi: dict[int, list[int]] = {i: sorted(adj[i]) for i in range(n)}
    for e in dummy:
        a, b = tuple(e)
        multi[a].append(b)
        multi[b].append(a)
    used: dict[frozenset, int] = {}
    for i in range(n):
        for j in multi[i]:
            if i < j:
                key = frozenset((i, j))
                used[key] = used.get(key, 0) + 1
    remaining = dict(used)
    stack, circuit_edges = [0], []
    ptr = {i: 0 for i in range(n)}
    # Hierholzer on the multigraph; record each traversed edge with its direction.
    edge_stack: list[tuple[int, int]] = []
    while stack:
        v = stack[-1]
        while ptr[v] < len(multi[v]) and remaining.get(frozenset((v, multi[v][ptr[v]])), 0) == 0:
            ptr[v] += 1
        if ptr[v] < len(multi[v]):
            w = multi[v][ptr[v]]
            remaining[frozenset((v, w))] -= 1
            stack.append(w)
            edge_stack.append((v, w))
        else:
            stack.pop()
            if edge_stack:
                circuit_edges.append(edge_stack.pop())
    oriented: set[tuple[str, str]] = set()
    dummy_left = set(dummy)
    for v, w in circuit_edges:
        key = frozenset((v, w))
        if key in dummy_left and (teams[v], teams[w]) not in oriented and (teams[w], teams[v]) not in oriented:
            # The first traversal of a doubled pair is the dummy copy; skip it.
            dummy_left.discard(key)
            continue
        oriented.add((teams[v], teams[w]))
    return oriented


def circle_rounds(teams: list[str]) -> list[list[tuple[str | None, str | None]]]:
    """One leg of pairings. None marks the phantom opponent (bye) when the team count is odd."""
    arr: list[str | None] = list(teams)
    if len(arr) % 2:
        arr.append(None)
    n = len(arr)
    home_of = _balanced_orientation(list(teams))
    rounds = []
    for _ in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            if a is not None and b is not None and (a, b) not in home_of:
                a, b = b, a
            pairs.append((a, b))
        rounds.append(pairs)
        arr = [arr[0], arr[-1]] + arr[1:-1]
    return rounds


def generate(teams: list[str], params: dict) -> dict:
    legs = params.get("legs", 1)
    if legs is None:
        legs = 1
    if not is_int(legs) or legs not in (1, 2):
        raise validation("legs")
    policy = params.get("withdrawal_policy", "forfeit_remaining") or "forfeit_remaining"
    if policy not in ("forfeit_remaining", "void_all"):
        raise validation("withdrawal_policy")
    withdrawals = params.get("withdrawals") or []
    if not isinstance(withdrawals, list):
        raise validation("withdrawals")

    base = circle_rounds(teams)
    per_leg = len(base)
    round_count = per_leg * legs

    withdrawn: dict[str, int] = {}
    for w in withdrawals:
        if not isinstance(w, dict) or w.get("team_id") not in teams:
            raise validation("withdrawals")
        after = w.get("after_round")
        if not is_int(after) or not (0 <= after <= round_count):
            raise validation("withdrawals")
        withdrawn[w["team_id"]] = after

    rounds_out = []
    summary = {"total": 0, "scheduled": 0, "forfeit": 0, "voided": 0}
    for leg in range(1, legs + 1):
        for r_idx, pairs in enumerate(base):
            rnd = (leg - 1) * per_leg + r_idx + 1
            matches, byes = [], []
            for a, b in pairs:
                if a is None or b is None:
                    byes.append(a if b is None else b)
                    continue
                home, away = (a, b) if leg == 1 else (b, a)
                status, awarded = _apply_withdrawal(home, away, rnd, withdrawn, policy)
                matches.append({
                    "match_id": f"RR-L{leg}-R{rnd}-M{len(matches) + 1}",
                    "leg": leg, "home": home, "away": away,
                    "status": status, "awarded_to": awarded,
                })
                summary["total"] += 1
                summary[status] += 1
            rounds_out.append({"round": rnd, "matches": matches, "byes": byes})

    return {"format": "round_robin", "legs": legs, "team_count": len(teams), "round_count": round_count,
            "rounds": rounds_out, "summary": summary}


def _apply_withdrawal(home: str, away: str, rnd: int, withdrawn: dict, policy: str):
    if policy == "void_all":
        if home in withdrawn or away in withdrawn:
            return "voided", None
        return "scheduled", None
    home_out = home in withdrawn and rnd > withdrawn[home]
    away_out = away in withdrawn and rnd > withdrawn[away]
    if home_out and away_out:
        return "voided", None
    if home_out:
        return "forfeit", away
    if away_out:
        return "forfeit", home
    return "scheduled", None
