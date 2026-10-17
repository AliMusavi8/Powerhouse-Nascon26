"""Swiss-system pairing for one round (spec 5.7-B).

Scores are kept in half-points (win = 2, draw = 1) so all comparisons are exact integers.
"""
import math

from ...errors import ApiError, validation
from ..validate import is_int


def standings(teams: list[str], history: list[dict]):
    idx = {t: i for i, t in enumerate(teams)}
    score = {t: 0 for t in teams}
    opponents: dict[str, list[str]] = {t: [] for t in teams}
    played: set[frozenset] = set()
    had_bye: set[str] = set()
    for rnd in history:
        bye = rnd.get("bye")
        if bye is not None:
            score[bye] += 2
            had_bye.add(bye)
        for m in rnd.get("matches", []):
            h, a, res = m["home"], m["away"], m["result"]
            opponents[h].append(a)
            opponents[a].append(h)
            played.add(frozenset((h, a)))
            if res == "home":
                score[h] += 2
            elif res == "away":
                score[a] += 2
            else:
                score[h] += 1
                score[a] += 1
    buchholz = {t: sum(score[o] for o in opponents[t]) for t in teams}
    order = sorted(teams, key=lambda t: (-score[t], -buchholz[t], idx[t]))
    table = [{"rank": r + 1, "team_id": t, "score": score[t] / 2, "buchholz": buchholz[t] / 2}
             for r, t in enumerate(order)]
    return score, buchholz, played, had_bye, order, table


def min_cost_pairing(players: list[str], score: dict, played: set[frozenset]):
    """Rematch-free perfect matching minimising the sum of |score difference|.

    Branch and bound: pair the first unpaired player with each candidate (closest score first).
    Lower bound for a remaining set = adjacent pairing of the score-sorted set (the unconstrained
    1-D optimum). A memo of the best accumulated cost per remaining set prunes revisits.
    """
    ordered = sorted(players, key=lambda p: -score[p])
    n = len(ordered)
    if n == 0:
        return 0, []
    s = [score[p] for p in ordered]
    forbidden = [[frozenset((ordered[i], ordered[j])) in played for j in range(n)] for i in range(n)]
    best = {"cost": math.inf, "pairs": None}
    seen: dict[int, int] = {}

    def lower_bound(mask: int) -> int:
        vals = [s[i] for i in range(n) if mask >> i & 1]
        return sum(vals[k] - vals[k + 1] for k in range(0, len(vals) - 1, 2))

    def dfs(mask: int, cost: int, pairs: list):
        if mask == 0:
            if cost < best["cost"]:
                best["cost"], best["pairs"] = cost, list(pairs)
            return
        if cost + lower_bound(mask) >= best["cost"]:
            return
        prev = seen.get(mask)
        if prev is not None and prev <= cost:
            return
        seen[mask] = cost
        i = (mask & -mask).bit_length() - 1
        rest = mask & ~(1 << i)
        cands = [j for j in range(n) if rest >> j & 1 and not forbidden[i][j]]
        cands.sort(key=lambda j: (abs(s[i] - s[j]), j))
        for j in cands:
            pairs.append((i, j))
            dfs(rest & ~(1 << j), cost + abs(s[i] - s[j]), pairs)
            pairs.pop()

    dfs((1 << n) - 1, 0, [])
    if best["pairs"] is None:
        return None, None
    return best["cost"], [(ordered[i], ordered[j]) for i, j in best["pairs"]]


def generate(teams: list[str], params: dict) -> dict:
    n = len(teams)
    total_rounds = params.get("total_rounds")
    if total_rounds is None:
        total_rounds = max(1, min(n - 1, math.ceil(math.log2(n))))
    if not is_int(total_rounds) or not (1 <= total_rounds <= n - 1):
        raise validation("total_rounds")
    rnd = params.get("round", 1)
    if rnd is None:
        rnd = 1
    if not is_int(rnd) or not (1 <= rnd <= total_rounds):
        raise validation("round")
    history = params.get("history") or []
    _validate_history(history, teams, rnd)

    score, _, played, had_bye, order, table = standings(teams, history)
    idx = {t: i for i, t in enumerate(teams)}

    if rnd == 1:
        m = n // 2
        pairs = [(teams[i], teams[i + m]) for i in range(m)]
        bye = teams[-1] if n % 2 else None
    else:
        pairs, bye = None, None
        if n % 2:
            pool = [t for t in teams if t not in had_bye] or list(teams)
            candidates = sorted(pool, key=lambda t: (score[t], -idx[t]))
            for cand in candidates:
                _, found = min_cost_pairing([t for t in teams if t != cand], score, played)
                if found is not None:
                    pairs, bye = found, cand
                    break
        else:
            _, pairs = min_cost_pairing(list(teams), score, played)
        if pairs is None:
            raise ApiError(409, "NO_VALID_PAIRING", f"No rematch-free pairing exists for round {rnd}.",
                           {"round": rnd})
        rank = {t: r for r, t in enumerate(order)}
        pairs = [(a, b) if rank[a] <= rank[b] else (b, a) for a, b in pairs]
        pairs.sort(key=lambda p: rank[p[0]])

    pairings = [{"match_id": f"SW-R{rnd}-M{i + 1}", "home": h, "away": a} for i, (h, a) in enumerate(pairs)]
    return {"format": "swiss", "round": rnd, "total_rounds": total_rounds, "pairings": pairings,
            "bye": bye, "standings": table}


def _validate_history(history, teams: list[str], rnd: int) -> None:
    if not isinstance(history, list):
        raise validation("history")
    team_set = set(teams)
    rounds = []
    for h in history:
        if not isinstance(h, dict) or not is_int(h.get("round")):
            raise validation("history")
        rounds.append(h["round"])
        bye = h.get("bye")
        if bye is not None and bye not in team_set:
            raise validation("history")
        matches = h.get("matches", [])
        if not isinstance(matches, list):
            raise validation("history")
        for m in matches:
            if (not isinstance(m, dict) or m.get("home") not in team_set or m.get("away") not in team_set
                    or m.get("home") == m.get("away") or m.get("result") not in ("home", "away", "draw")):
                raise validation("history")
    if sorted(rounds) != list(range(1, rnd)):
        raise validation("history")
