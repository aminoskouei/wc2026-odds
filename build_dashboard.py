#!/usr/bin/env python3
"""Inject teams data + latest simulation odds into the dashboard.

Usage:  python build_dashboard.py
Reads:  teams.json, odds.json, dashboard_template.html
Writes: index.html  (single self-contained file — GitHub Pages ready)
"""
import json
from pathlib import Path

teams = json.load(open("teams.json"))
odds = json.load(open("odds.json"))

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
Path("index.html").write_text(tpl.replace("__DATA_PLACEHOLDER__", blob))
print(f"index.html built ({len(blob):,} bytes of data, "
      f"{payload['sims']:,} sims)")
