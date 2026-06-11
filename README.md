# ⚽ World Cup 2026 Odds Board

Monte Carlo simulation + interactive dashboard for the 2026 FIFA World Cup
(USA · Mexico · Canada, June 11 – July 19, 2026). All **48 teams**, **12 groups**,
**104 matches** — and championship odds from **100,000 simulated tournaments**,
inspired by Nate Silver's [PELE model](https://www.natesilver.net/p/world-cup-2026-odds-predictions).

## Quick start

```bash
pip install numpy

# 1. Run the simulation (100k tournaments ≈ 1 minute)
python simulate.py -n 100000

# 2. Bake results into the dashboard
python build_dashboard.py

# 3. Open index.html in a browser (or push to GitHub Pages)
```

`index.html` is fully self-contained — no server, no build tools, no API
keys. Drop it on GitHub Pages and you're live.

## What's in the dashboard

- **Title Odds** — all 48 teams ranked by championship probability, with fair
  decimal & American odds and semifinal probabilities
- **Groups & Teams** — all 12 groups with each team's marquee player, model
  rating, win-group odds, storyline, and search/filter by confederation
- **Schedule** — marquee fixtures, the knockout calendar (R32 → Final at
  New York/New Jersey Stadium on July 19), and every group's playing window
- **Model** — full methodology writeup

## How the model works

1. **Ratings.** Every team carries an Elo-style rating
   (`teams.json` — edit freely). Hosts get a home-advantage bonus:
   Mexico's is largest (Azteca altitude), USA/Canada smaller, all reduced
   in the knockout rounds.
2. **Matches.** The Elo gap drives expected goals; scorelines come from
   independent Poisson draws:
   `μ = 1.30 · exp(±0.0045 · ΔElo / 2)`.
3. **Format.** Full 2026 rules: 12 groups with FIFA tiebreakers
   (points → head-to-head → goal difference → goals scored), best 8
   third-place teams advance, then a 32-team knockout bracket. Drawn
   knockout games go to ET/penalties with a dampened Elo edge.
4. **Odds.** Championship probability = title share across all runs;
   fair odds = 1 / probability (no bookmaker margin).

**Known simplification:** the real third-place bracket allocation depends on
*which* 8 groups produce qualifying thirds (495 combinations); we assign
qualifying thirds to bracket slots randomly each run. Effect on title odds
is small but nonzero.

## CLI

```bash
python simulate.py -n 100000          # number of simulations
python simulate.py --seed 7           # reproducible runs
python simulate.py -o odds.json
```

## Updating the data — do you need API keys?

The repo runs **with zero API keys**. To make it live-updating:

| Data | Source | Key? |
|---|---|---|
| Team Elo ratings | [eloratings.net](https://eloratings.net) (CSV-ish, scrapeable) | No |
| FIFA rankings | [FIFA](https://inside.fifa.com/fifa-world-ranking/men) | No |
| Fixtures, results, squads | [football-data.org](https://www.football-data.org) | Free key |
| Fixtures, lineups, stats | [API-Football](https://www.api-football.com) | Free tier key |
| Live sportsbook odds (to compare vs. model) | [The Odds API](https://the-odds-api.com) | Free key |

A natural next step: a small `update_ratings.py` that pulls live Elo after each
matchday, hardcodes played results, and re-simulates the remainder — exactly
how PELE updates in-tournament.

## Project layout

```
├── simulate.py             # Monte Carlo engine (numpy only)
├── build_dashboard.py      # injects data + odds into the dashboard
├── dashboard_template.html # UI template
├── index.html              # generated, self-contained dashboard
├── teams.json              # 48 teams: groups, ratings, stars, notes
└── odds.json               # generated simulation results
```

## Disclaimers

Model output, not betting advice. Fair odds exclude bookmaker margin, so real
market prices will always be shorter. Ratings are a hand-calibrated
pre-tournament snapshot (anchored to market consensus of Spain/France as
co-favorites); star players and notes are indicative as of June 11, 2026.

MIT License.
