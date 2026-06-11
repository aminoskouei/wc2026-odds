#!/usr/bin/env python3
"""Inject teams data + latest simulation odds into the dashboard.

Usage:  python build_dashboard.py
Reads:  data/teams.json, output/odds.json, dashboard_template.html
Writes: dashboard.html  (single self-contained file — GitHub Pages ready)
"""
import json
from pathlib import Path

teams = json.load(open("data/teams.json"))
odds = json.load(open("output/odds.json"))

payload = {
    "sims": odds["meta"]["simulations"],
    "teams": teams["teams"],
    "groups": teams["groups"],
    "windows": teams["group_stage_windows"],
    "ko": teams["knockout_dates"],
    "fixtures": teams["marquee_fixtures"],
    "odds": odds["teams"],
}

tpl = Path("dashboard_template.html").read_text()
blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
Path("dashboard.html").write_text(tpl.replace("__DATA_PLACEHOLDER__", blob))
print(f"dashboard.html built ({len(blob):,} bytes of data, "
      f"{payload['sims']:,} sims)")
