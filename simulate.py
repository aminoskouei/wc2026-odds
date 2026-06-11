#!/usr/bin/env python3
"""
World Cup 2026 Monte Carlo Simulator
=====================================
Simulates the full 48-team / 12-group / Round-of-32 format N times
(inspired by Nate Silver's PELE / FiveThirtyEight SPI approach) and
produces title odds, stage-by-stage advancement probabilities, and
fair betting prices for every team.

Model:
  - Each team has an Elo-style rating (data/teams.json). Defaults are a
    static pre-tournament snapshot blending Elo / FIFA-ranking intuition;
    swap in live ratings from eloratings.net or your own model anytime.
  - Hosts (USA, Mexico, Canada) get a home-advantage Elo bonus in the
    group stage and a reduced bonus in knockouts (most knockout games
    are in the US, so the edge dilutes).
  - Match scores are drawn from independent Poisson distributions whose
    means are driven by the Elo gap (more gap -> more goals for the
    favorite, fewer against).
  - Group tiebreakers: points -> head-to-head points among tied teams ->
    goal difference -> goals scored -> random (proxy for fair-play pts
    and FIFA ranking).
  - Best 8 of 12 third-place teams advance (points/GD/GF), then a
    32-team single-elimination bracket. Knockout draws go to "extra
    time + penalties," modeled as a win probability with the Elo edge
    dampened (penalties are close to a coin flip).

Usage:
  python simulate.py                 # 20,000 sims (default)
  python simulate.py -n 100000       # match Silver's 100k
  python simulate.py -n 50000 --seed 7 -o output/odds.json

No API keys needed. Pure standard library + numpy.
"""

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Model constants (tune these)
# ---------------------------------------------------------------------------
BASE_GOALS = 1.30          # avg goals per team in an even match
ELO_GOAL_SLOPE = 0.0045    # how fast expected goals scale with Elo gap
HOME_BONUS_GROUP = {       # Elo bonus, group stage (all home games)
    "Mexico": 155,         # Azteca altitude — biggest home edge in PELE
    "United States": 90,
    "Canada": 90,
}
HOME_BONUS_KO = {          # knockouts: most games in the US
    "Mexico": 60, "United States": 80, "Canada": 40,
}
KO_PENALTY_DAMPING = 0.55  # how much Elo edge survives into pens/ET
DRAW_TO_PENS = 0.50        # share of level-after-90 games decided ~50/50-ish

# Official-style R32 pairings: group winners vs runners-up / thirds.
# The real FIFA bracket maps specific groups to specific slots; the exact
# third-place allocation depends on WHICH 8 groups produce qualifying
# thirds (495 combos), so we approximate: winners face thirds or
# runners-up per the template below, with qualifying thirds assigned
# randomly to the third-place slots each simulation.
R32_TEMPLATE = [
    ("1A", "3rd"), ("2B", "2D"), ("1C", "3rd"), ("1E", "3rd"),
    ("2A", "2C"), ("1F", "2H"), ("1G", "3rd"), ("1I", "3rd"),
    ("2E", "2G"), ("1J", "2K"), ("1B", "3rd"), ("1D", "3rd"),
    ("2F", "2I"), ("1H", "2L"), ("1K", "3rd"), ("1L", "2J"),
]


def load_data(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def expected_goals(elo_a: float, elo_b: float) -> tuple[float, float]:
    """Expected goals for A and B given their (adjusted) Elo ratings."""
    diff = elo_a - elo_b
    mu_a = BASE_GOALS * math.exp(ELO_GOAL_SLOPE * diff * 0.5)
    mu_b = BASE_GOALS * math.exp(-ELO_GOAL_SLOPE * diff * 0.5)
    return mu_a, mu_b


def adj_rating(team: str, rating: float, stage: str) -> float:
    bonus = (HOME_BONUS_GROUP if stage == "group" else HOME_BONUS_KO)
    return rating + bonus.get(team, 0)


def sim_match(rng, team_a, team_b, ratings, stage="group"):
    """Returns (goals_a, goals_b)."""
    ra = adj_rating(team_a, ratings[team_a], stage)
    rb = adj_rating(team_b, ratings[team_b], stage)
    mu_a, mu_b = expected_goals(ra, rb)
    return rng.poisson(mu_a), rng.poisson(mu_b)


def sim_knockout_winner(rng, team_a, team_b, ratings):
    """Single-elimination match: returns the winner."""
    ga, gb = sim_match(rng, team_a, team_b, ratings, stage="ko")
    if ga > gb:
        return team_a
    if gb > ga:
        return team_b
    # Extra time + penalties: dampened Elo edge
    ra = adj_rating(team_a, ratings[team_a], "ko")
    rb = adj_rating(team_b, ratings[team_b], "ko")
    diff = (ra - rb) * KO_PENALTY_DAMPING
    p_a = 1.0 / (1.0 + 10 ** (-diff / 400.0))
    return team_a if rng.random() < p_a else team_b


def rank_group(table, h2h, rng_py):
    """FIFA-style group ranking. table: {team: [pts, gd, gf]}."""
    teams = list(table.keys())

    def sort_key(t):
        return (table[t][0], table[t][1], table[t][2], rng_py.random())

    teams.sort(key=sort_key, reverse=True)

    # Head-to-head correction for teams level on points
    # (2026 rules: H2H comes before overall GD)
    i = 0
    while i < len(teams):
        j = i
        while j + 1 < len(teams) and table[teams[j + 1]][0] == table[teams[i]][0]:
            j += 1
        if j > i:
            tied = teams[i:j + 1]
            tied.sort(
                key=lambda t: (
                    sum(h2h[t].get(o, (0, 0))[0] for o in tied if o != t),  # h2h pts
                    sum(h2h[t].get(o, (0, 0))[1] for o in tied if o != t),  # h2h gd
                    table[t][1], table[t][2], rng_py.random(),
                ),
                reverse=True,
            )
            teams[i:j + 1] = tied
        i = j + 1
    return teams


def simulate_once(rng, rng_py, groups, ratings, counters):
    group_results = {}   # letter -> ranked list of teams
    third_pool = []      # (pts, gd, gf, rand, team)

    # ---- Group stage ----
    for letter, members in groups.items():
        table = {t: [0, 0, 0] for t in members}        # pts, gd, gf
        h2h = {t: {} for t in members}
        for i in range(4):
            for j in range(i + 1, 4):
                a, b = members[i], members[j]
                ga, gb = sim_match(rng, a, b, ratings, "group")
                table[a][1] += ga - gb; table[a][2] += ga
                table[b][1] += gb - ga; table[b][2] += gb
                if ga > gb:
                    table[a][0] += 3
                    h2h[a][b] = (3, ga - gb); h2h[b][a] = (0, gb - ga)
                elif gb > ga:
                    table[b][0] += 3
                    h2h[b][a] = (3, gb - ga); h2h[a][b] = (0, ga - gb)
                else:
                    table[a][0] += 1; table[b][0] += 1
                    h2h[a][b] = (1, 0); h2h[b][a] = (1, 0)

        ranked = rank_group(table, h2h, rng_py)
        group_results[letter] = ranked
        t3 = ranked[2]
        third_pool.append((table[t3][0], table[t3][1], table[t3][2],
                           rng_py.random(), t3))
        counters["win_group"][ranked[0]] += 1

    # ---- Best 8 third-place teams ----
    third_pool.sort(reverse=True)
    thirds = [t[-1] for t in third_pool[:8]]
    rng_py.shuffle(thirds)

    advancers = set(thirds)
    for letter, ranked in group_results.items():
        advancers.update(ranked[:2])
    for t in advancers:
        counters["r32"][t] += 1

    # ---- Build Round of 32 ----
    slot = {}
    for letter, ranked in group_results.items():
        slot[f"1{letter}"] = ranked[0]
        slot[f"2{letter}"] = ranked[1]

    third_iter = iter(thirds)
    matches = []
    for a_key, b_key in R32_TEMPLATE:
        a = slot[a_key]
        b = next(third_iter) if b_key == "3rd" else slot[b_key]
        matches.append((a, b))

    # ---- Knockout rounds ----
    rnd = matches
    round_names = ["r16", "qf", "sf", "final_app"]
    name_idx = 0
    while len(rnd) > 1:
        winners = []
        for a, b in rnd:
            winners.append(sim_knockout_winner(rng, a, b, ratings))
        for w in winners:
            counters[round_names[name_idx]][w] += 1
        rnd = [(winners[k], winners[k + 1]) for k in range(0, len(winners), 2)]
        name_idx += 1

    champ = sim_knockout_winner(rng, rnd[0][0], rnd[0][1], ratings)
    counters["champion"][champ] += 1


def to_odds(p: float) -> dict:
    """Convert probability to fair betting prices."""
    if p <= 0:
        return {"decimal": None, "american": None}
    dec = 1.0 / p
    if p >= 0.5:
        amer = -round(100 * p / (1 - p)) if p < 1 else None
    else:
        amer = round(100 * (1 - p) / p)
    return {"decimal": round(dec, 2),
            "american": f"+{amer}" if isinstance(amer, int) and amer > 0 else str(amer)}


def main():
    ap = argparse.ArgumentParser(description="World Cup 2026 Monte Carlo simulator")
    ap.add_argument("-n", "--sims", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("-d", "--data", default="teams.json")
    ap.add_argument("-o", "--out", default="odds.json")
    args = ap.parse_args()

    data = load_data(Path(args.data))
    groups = data["groups"]
    ratings = {t: info["rating"] for t, info in data["teams"].items()}

    rng = np.random.default_rng(args.seed)
    rng_py = random.Random(args.seed)

    stages = ["win_group", "r32", "r16", "qf", "sf", "final_app", "champion"]
    counters = {s: defaultdict(int) for s in stages}

    print(f"Running {args.sims:,} tournament simulations...")
    for k in range(args.sims):
        simulate_once(rng, rng_py, groups, ratings, counters)
        if (k + 1) % max(1, args.sims // 10) == 0:
            print(f"  {k + 1:,} / {args.sims:,}")

    n = args.sims
    results = {}
    for team in ratings:
        p_champ = counters["champion"][team] / n
        results[team] = {
            "group": data["teams"][team]["group"],
            "rating": ratings[team],
            "p_win_group": round(counters["win_group"][team] / n, 4),
            "p_reach_r32": round(counters["r32"][team] / n, 4),
            "p_reach_r16": round(counters["r16"][team] / n, 4),
            "p_reach_qf": round(counters["qf"][team] / n, 4),
            "p_reach_sf": round(counters["sf"][team] / n, 4),
            "p_reach_final": round(counters["final_app"][team] / n, 4),
            "p_champion": round(p_champ, 4),
            "fair_odds": to_odds(p_champ),
        }

    out = {
        "meta": {
            "simulations": n,
            "seed": args.seed,
            "model": "Elo + Poisson Monte Carlo, 2026 48-team format",
        },
        "teams": dict(sorted(results.items(),
                             key=lambda kv: -kv[1]["p_champion"])),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n{'TEAM':<24}{'WIN%':>7}{'FAIR (DEC)':>12}{'AMERICAN':>10}{'  SF%':>7}")
    print("-" * 60)
    for team, r in list(out["teams"].items())[:15]:
        fo = r["fair_odds"]
        print(f"{team:<24}{r['p_champion']*100:>6.1f}%"
              f"{fo['decimal'] or '-':>12}{fo['american'] or '-':>10}"
              f"{r['p_reach_sf']*100:>6.1f}%")
    print(f"\nSaved full results -> {out_path}")


if __name__ == "__main__":
    main()
