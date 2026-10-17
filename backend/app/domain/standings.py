"""League standings (spec 5.10): table, recursive tie-breaks, head-to-head and qualification status.

Input `results` is one entry per fixture, derived from the score projections:
    {"home", "away", "played", "result": "home"|"away"|"draw",
     "hs", "as", "hf", "af", "hb", "ab", "hw", "aw"}   (score, fair play, legal balls, wickets)
"""
from ..crypto import lots_key


class Table:
    def __init__(self, cfg: dict, sport: dict, results: list[dict]):
        self.cfg, self.sport, self.results = cfg, sport, results
        self.teams = cfg["teams"]
        self.pts = cfg["points"]
        self.model = sport["scoring_model"]
        self.played = [r for r in results if r["played"]]

    # ------------------------------------------------------------------ aggregates

    def _overs(self, balls: int, wickets: int) -> float:
        p = self.sport["periods"]
        if wickets >= p["innings_per_team"] * p["wickets_per_innings"]:
            return float(p["innings_per_team"] * p["overs_per_innings"])
        return balls / p["balls_per_over"]

    def stats(self, team: str, matches: list[dict]) -> dict:
        s = {"played": 0, "won": 0, "drawn": 0, "lost": 0, "scored": 0, "conceded": 0, "fair_play": 0,
             "points": 0, "of": 0.0, "ob": 0.0}
        for r in matches:
            if team == r["home"]:
                me, opp, sc, co, fp = "home", "away", r["hs"], r["as"], r["hf"]
                faced, bowled = self._overs_for(r, "h"), self._overs_for(r, "a")
            elif team == r["away"]:
                me, opp, sc, co, fp = "away", "home", r["as"], r["hs"], r["af"]
                faced, bowled = self._overs_for(r, "a"), self._overs_for(r, "h")
            else:
                continue
            s["played"] += 1
            s["scored"] += sc
            s["conceded"] += co
            s["fair_play"] += fp
            s["of"] += faced
            s["ob"] += bowled
            if r["result"] == me:
                s["won"] += 1
            elif r["result"] == opp:
                s["lost"] += 1
            else:
                s["drawn"] += 1
        s["points"] = s["won"] * self.pts["win"] + s["drawn"] * self.pts["draw"] + s["lost"] * self.pts["loss"]
        s["diff"] = self._diff(s)
        return s

    def _overs_for(self, r: dict, side: str) -> float:
        if self.model != "innings":
            return 0.0
        return self._overs(r[side + "b"], r[side + "w"])

    def _diff(self, s: dict):
        if self.model != "innings":
            return s["scored"] - s["conceded"]
        rate_for = s["scored"] / s["of"] if s["of"] else 0.0
        rate_against = s["conceded"] / s["ob"] if s["ob"] else 0.0
        return round(rate_for - rate_against, 3)

    # ------------------------------------------------------------------ ordering

    def criterion(self, name: str, group: list[str]) -> dict:
        if name in ("h2h_points", "h2h_diff"):
            gs = set(group)
            mini = [r for r in self.played if r["home"] in gs and r["away"] in gs]
            key = "points" if name == "h2h_points" else "diff"
            return {t: self.stats(t, mini)[key] for t in group}
        if name == "overall_diff":
            return {t: self.overall[t]["diff"] for t in group}
        if name == "scored":
            return {t: self.overall[t]["scored"] for t in group}
        if name == "fair_play":
            return {t: self.overall[t]["fair_play"] for t in group}
        # draw_lots: lower hash is better, so negate the rank.
        ordered = sorted(group, key=lambda t: lots_key(self.cfg["lots_seed"], self.cfg["league_id"], t))
        return {t: -i for i, t in enumerate(ordered)}

    def resolve(self, group: list[str]) -> list[str]:
        order = [c for c in self.cfg["tie_break_order"] if c != "draw_lots"] + ["draw_lots"]
        for name in order:
            values = self.criterion(name, group)
            distinct = sorted(set(values.values()), reverse=True)
            if len(distinct) == 1:
                continue
            result: list[str] = []
            for v in distinct:
                sub = [t for t in group if values[t] == v]
                if result:
                    self.resolved_by[result[-1]] = name
                result.extend(self.resolve(sub) if len(sub) > 1 else sub)
            return result
        return list(group)

    def compute(self) -> dict:
        self.overall = {t: self.stats(t, self.played) for t in self.teams}
        self.resolved_by: dict[str, str] = {}
        by_points: dict[int, list[str]] = {}
        for t in self.teams:
            by_points.setdefault(self.overall[t]["points"], []).append(t)
        ordered: list[str] = []
        for p in sorted(by_points, reverse=True):
            g = by_points[p]
            ordered.extend(self.resolve(g) if len(g) > 1 else g)

        remaining = {t: 0 for t in self.teams}
        for r in self.results:
            if not r["played"]:
                remaining[r["home"]] += 1
                remaining[r["away"]] += 1
        k = self.cfg["spots"]
        w = self.pts["win"]
        points = {t: self.overall[t]["points"] for t in self.teams}
        max_pts = {t: points[t] + w * remaining[t] for t in self.teams}

        table = []
        for rank, t in enumerate(ordered, start=1):
            others = [x for x in self.teams if x != t]
            if sum(1 for x in others if max_pts[x] >= points[t]) < k:
                status = "clinched"
            elif sum(1 for x in others if points[x] > max_pts[t]) >= k:
                status = "eliminated"
            else:
                status = "still_possible"
            s = self.overall[t]
            table.append({"rank": rank, "team_id": t, "played": s["played"], "won": s["won"], "drawn": s["drawn"],
                          "lost": s["lost"], "scored": s["scored"], "conceded": s["conceded"], "diff": s["diff"],
                          "points": s["points"], "fair_play": s["fair_play"], "status": status,
                          "resolved_by": self.resolved_by.get(t)})

        h2h = {}
        for a in self.teams:
            h2h[a] = {}
            for b in self.teams:
                if a == b:
                    continue
                pair = [r for r in self.played if {r["home"], r["away"]} == {a, b}]
                s = self.stats(a, pair)
                h2h[a][b] = {"played": s["played"], "points": s["points"], "scored": s["scored"],
                             "conceded": s["conceded"]}
        return {"table": table, "h2h": h2h}


def result_from_projection(fixture: dict, proj: dict | None) -> dict:
    """Map a score projection to the compact fixture result used by Table."""
    r = {"home": fixture["home"], "away": fixture["away"], "played": False, "result": None,
         "hs": 0, "as": 0, "hf": 0, "af": 0, "hb": 0, "ab": 0, "hw": 0, "aw": 0}
    if proj is None or proj["status"] != "completed" or proj["outcome"] == "undecided":
        return r
    h, a = proj["home"], proj["away"]
    r.update(played=True,
             result={"home_win": "home", "away_win": "away"}.get(proj["outcome"], "draw"),
             hs=h["score"], **{"as": a["score"]}, hf=h["fair_play"], af=a["fair_play"],
             hb=h["balls"] or 0, ab=a["balls"] or 0, hw=h["wickets"] or 0, aw=a["wickets"] or 0)
    return r
