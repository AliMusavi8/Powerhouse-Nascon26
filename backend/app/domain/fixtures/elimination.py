"""Single and double elimination brackets (spec 5.7-C and 5.7-D)."""
from ...errors import validation


def seed_order(size: int) -> list[int]:
    order = [1, 2]
    while len(order) < size:
        k2 = len(order) * 2
        order = [x for s in order for x in (s, k2 + 1 - s)]
    return order[:size]


def bracket_size(n: int) -> int:
    b = 1
    while b < n:
        b *= 2
    return max(b, 2)


def _match(match_id: str, bracket: str, rnd: int, index: int) -> dict:
    return {"match_id": match_id, "bracket": bracket, "round": rnd, "index": index,
            "home": None, "away": None, "home_seed": None, "away_seed": None, "bye": False,
            "winner": None, "loser": None, "winner_to": None, "loser_to": None}


class Bracket:
    def __init__(self, teams: list[str]):
        self.teams = teams
        self.seed_of = {t: i + 1 for i, t in enumerate(teams)}
        self.matches: dict[str, dict] = {}

    def add(self, m: dict) -> dict:
        self.matches[m["match_id"]] = m
        return m

    def place(self, target: dict | None, team: str | None) -> None:
        if target is None or team is None:
            return
        m = self.matches[target["match_id"]]
        m[target["slot"]] = team
        m[target["slot"] + "_seed"] = self.seed_of.get(team)
        self.on_change(m)

    def on_change(self, m: dict) -> None:
        """Hook for dependent matches (grand-final reset)."""

    def decide(self, m: dict, winner: str) -> None:
        loser = m["away"] if winner == m["home"] else m["home"]
        m["winner"], m["loser"] = winner, loser
        self.place(m["winner_to"], winner)
        self.place(m["loser_to"], loser)
        self.on_change(m)

    def seed_round_one(self, prefix: str, bracket: str, n: int, size: int) -> list[dict]:
        order = seed_order(size)
        first = []
        for i in range(size // 2):
            m = self.add(_match(f"{prefix}1M{i + 1}", bracket, 1, i + 1))
            hs, as_ = order[2 * i], order[2 * i + 1]
            m["home"], m["home_seed"] = self.teams[hs - 1], hs
            if as_ <= n:
                m["away"], m["away_seed"] = self.teams[as_ - 1], as_
            else:
                m["bye"] = True
            first.append(m)
        return first

    def propagate_byes(self, round_one: list[dict]) -> None:
        for m in round_one:
            if m["bye"]:
                m["winner"] = m["home"]
                self.place(m["winner_to"], m["home"])

    def apply_results(self, results) -> None:
        if results is None:
            return
        if not isinstance(results, list):
            raise validation("results")
        pending = []
        for r in results:
            if not isinstance(r, dict) or not isinstance(r.get("match_id"), str) or not isinstance(r.get("winner"), str):
                raise validation("results")
            if r["match_id"] not in self.matches:
                raise validation("results", f"Unknown match_id {r['match_id']}.")
            pending.append(r)
        # Results may arrive in any order; apply whatever is decidable until nothing changes.
        while pending:
            progressed, left = False, []
            for r in pending:
                m = self.matches[r["match_id"]]
                if r["winner"] in (m["home"], m["away"]) and r["winner"] is not None:
                    self.decide(m, r["winner"])
                    progressed = True
                else:
                    left.append(r)
            pending = left
            if not progressed:
                raise validation("results", "Winner is not a participant of the match.")


def _rounds(matches: list[dict]) -> list[dict]:
    out: dict[int, list] = {}
    for m in matches:
        out.setdefault(m["round"], []).append(m)
    return [{"round": r, "matches": ms} for r, ms in sorted(out.items())]


def _target(match_id: str, index: int) -> dict:
    return {"match_id": match_id, "slot": "home" if index % 2 == 1 else "away"}


def single_elim(teams: list[str], params: dict) -> dict:
    n = len(teams)
    size = bracket_size(n)
    k = size.bit_length() - 1
    br = Bracket(teams)
    r1 = br.seed_round_one("R", "main", n, size)
    for r in range(2, k + 1):
        for i in range(1, size // 2 ** r + 1):
            br.add(_match(f"R{r}M{i}", "main", r, i))
    for r in range(1, k):
        for i in range(1, size // 2 ** r + 1):
            br.matches[f"R{r}M{i}"]["winner_to"] = _target(f"R{r + 1}M{(i + 1) // 2}", i)
    third = params.get("third_place_match", False)
    if third is None:
        third = False
    if not isinstance(third, bool):
        raise validation("third_place_match")
    if third and k >= 2:
        br.add(_match("TP", "third_place", k, 1))
        br.matches[f"R{k - 1}M1"]["loser_to"] = {"match_id": "TP", "slot": "home"}
        br.matches[f"R{k - 1}M2"]["loser_to"] = {"match_id": "TP", "slot": "away"}
    br.propagate_byes(r1)
    br.apply_results(params.get("results"))
    main = [m for m in br.matches.values() if m["bracket"] == "main"]
    rounds = _rounds(main)
    if "TP" in br.matches:
        rounds[-1]["matches"].append(br.matches["TP"])
    return {"format": "single_elim", "bracket_size": size, "rounds": rounds}


class DoubleBracket(Bracket):
    def __init__(self, teams, reset: bool):
        super().__init__(teams)
        self.reset = reset

    def on_change(self, m: dict) -> None:
        if m["match_id"] != "GF1" or "GF2" not in self.matches:
            return
        gf2 = self.matches["GF2"]
        if m["winner"] is None:
            gf2["required"] = None
            return
        gf2["required"] = bool(self.reset and m["winner"] == m["away"])
        gf2["home"], gf2["away"] = m["home"], m["away"]
        gf2["home_seed"], gf2["away_seed"] = m["home_seed"], m["away_seed"]

    dead: set

    def decide(self, m: dict, winner: str) -> None:
        if m["match_id"] == "GF1":
            loser = m["away"] if winner == m["home"] else m["home"]
            m["winner"], m["loser"] = winner, loser
            self.on_change(m)
            return
        super().decide(m, winner)
        self.settle()

    def propagate_byes(self, round_one: list[dict]) -> None:
        self.dead = {(m["loser_to"]["match_id"], m["loser_to"]["slot"]) for m in round_one if m["bye"]}
        super().propagate_byes(round_one)
        self.settle()

    def settle(self) -> None:
        """Losers-bracket slots fed by a missing team never fill; advance the present team."""
        changed = True
        while changed:
            changed = False
            for m in self.matches.values():
                if m["bracket"] != "losers" or m["winner"] is not None or m.get("_void"):
                    continue
                hd = (m["match_id"], "home") in self.dead
                ad = (m["match_id"], "away") in self.dead
                if hd and ad:
                    m["_void"] = True
                    m["bye"] = True
                    if m["winner_to"]:
                        self.dead.add((m["winner_to"]["match_id"], m["winner_to"]["slot"]))
                    changed = True
                elif hd and m["away"] is not None or ad and m["home"] is not None:
                    present = m["away"] if hd else m["home"]
                    m["bye"] = True
                    m["winner"] = present
                    self.place(m["winner_to"], present)
                    changed = True


def double_elim(teams: list[str], params: dict) -> dict:
    n = len(teams)
    size = bracket_size(n)
    k = size.bit_length() - 1
    reset = params.get("bracket_reset", False)
    if reset is None:
        reset = False
    if not isinstance(reset, bool):
        raise validation("bracket_reset")
    br = DoubleBracket(teams, reset)
    wr1 = br.seed_round_one("WR", "winners", n, size)
    for r in range(2, k + 1):
        for i in range(1, size // 2 ** r + 1):
            br.add(_match(f"WR{r}M{i}", "winners", r, i))
    lr_rounds = 2 * (k - 1)
    for j in range(1, k):
        count = size // 2 ** (j + 1)
        for rr in (2 * j - 1, 2 * j):
            for i in range(1, count + 1):
                br.add(_match(f"LR{rr}M{i}", "losers", rr, i))
    gf1 = br.add(_match("GF1", "grand_final", 1, 1))
    gf1["conditional"], gf1["required"] = False, True
    if reset:
        gf2 = br.add(_match("GF2", "grand_final", 2, 1))
        gf2["conditional"], gf2["required"] = True, None
        gf1["winner_to"] = {"match_id": "GF2", "slot": "home"}
        gf1["loser_to"] = {"match_id": "GF2", "slot": "away"}

    # Winners bracket advancement and drops into the losers bracket.
    for r in range(1, k + 1):
        for i in range(1, size // 2 ** r + 1):
            m = br.matches[f"WR{r}M{i}"]
            if r < k:
                m["winner_to"] = _target(f"WR{r + 1}M{(i + 1) // 2}", i)
            else:
                m["winner_to"] = {"match_id": "GF1", "slot": "home"}
            if r == 1:
                m["loser_to"] = _target(f"LR1M{(i + 1) // 2}", i)
            else:
                m["loser_to"] = {"match_id": f"LR{2 * r - 2}M{i}", "slot": "away"}
    # Losers bracket advancement.
    for rr in range(1, lr_rounds + 1):
        count = size // 2 ** ((rr + 1) // 2 + 1)
        for i in range(1, count + 1):
            m = br.matches[f"LR{rr}M{i}"]
            if rr == lr_rounds:
                m["winner_to"] = {"match_id": "GF1", "slot": "away"}
            elif rr % 2 == 1:
                m["winner_to"] = {"match_id": f"LR{rr + 1}M{i}", "slot": "home"}
            else:
                m["winner_to"] = _target(f"LR{rr + 1}M{(i + 1) // 2}", i)

    br.propagate_byes(wr1)
    br.apply_results(params.get("results"))
    for m in br.matches.values():
        m.pop("_void", None)
    winners = [m for m in br.matches.values() if m["bracket"] == "winners"]
    losers = [m for m in br.matches.values() if m["bracket"] == "losers"]
    gf = [br.matches["GF1"]] + ([br.matches["GF2"]] if reset else [])
    return {"format": "double_elim", "bracket_size": size, "bracket_reset": reset,
            "winners": _rounds(winners), "losers": _rounds(losers), "grand_final": gf}
