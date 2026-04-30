#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_stats.py — Henter Vepsene-stats fra gamer.no og lagrer som stats.json
Brukes av GitHub Actions for automatisk oppdatering av nettsiden.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

COMPETITION_URL = "https://www.gamer.no/turneringer/komplettligaen-counter-strike-varen-2026/13835"
TEAM_ID = 84331
BASE_API = "https://www.gamer.no/api/paradise"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.5",
    "x-requested-with": "XMLHttpRequest",
})


def load_cookies_from_env():
    cookie = os.environ.get("GAMER_COOKIE", "")
    xsrf = os.environ.get("GAMER_XSRF", "")
    if cookie:
        SESSION.headers["cookie"] = cookie
        print("Cookies lastet fra miljøvariabler.")
    if xsrf:
        SESSION.headers["x-xsrf-token"] = xsrf
    if not cookie:
        print("ADVARSEL: Ingen cookies funnet. API-kall kan feile.")


def api_get(url):
    r = SESSION.get(url, timeout=45)
    r.raise_for_status()
    return r.json()


def get_comp_id():
    m = re.search(r'gamer\.no/turneringer/[^/]+/(\d+)', COMPETITION_URL)
    if m:
        return int(m.group(1))
    raise ValueError("Kunne ikke hente competition ID fra URL")


def get_phases(comp_id):
    return api_get(f"{BASE_API}/competition/{comp_id}/phases?page=1").get("data", [])


def get_player_stats(comp_id):
    data = api_get(
        f"{BASE_API}/competition/{comp_id}/stats/players/extended"
        f"?paradise_team_id={TEAM_ID}"
    )
    return data.get("data", [])


def get_matches(comp_id):
    try:
        data = api_get(f"{BASE_API}/competition/{comp_id}/matches?paradise_team_id={TEAM_ID}&limit=50")
        return data.get("data", [])
    except Exception as e:
        print(f"Kunne ikke hente kamper: {e}")
        return []


def main():
    load_cookies_from_env()

    comp_id = get_comp_id()
    print(f"Competition ID: {comp_id}")

    # Hent turneringsinfo
    comp_data = api_get(f"{BASE_API}/competition/{comp_id}")
    comp_name = comp_data.get("competition", {}).get("name", "Komplettligaen")

    # Hent spillerstatistikk
    print("Henter spillerstatistikk...")
    players = get_player_stats(comp_id)
    print(f"  {len(players)} spillere funnet")

    # Hent kamper
    print("Henter kamper...")
    raw_matches = get_matches(comp_id)

    # Formater spillerdata
    player_list = []
    for p in sorted(players, key=lambda x: x.get("rating") or 0, reverse=True):
        hs = p.get("headshot_ratio")
        traded = p.get("traded_deaths_ratio")
        player_list.append({
            "name": p.get("player_name") or p.get("user", {}).get("user_name", "Ukjent"),
            "rating": round(p.get("rating") or 0, 2),
            "kills": p.get("kills"),
            "assists": p.get("assists"),
            "deaths": p.get("deaths"),
            "kd_diff": p.get("kd_diff"),
            "adr": round(p.get("damage_per_round") or 0, 1),
            "hs_pct": round(hs * 100, 1) if hs is not None else None,
            "entry_kills": p.get("firstkills"),
            "clutches": p.get("clutches_won"),
            "k2": p.get("rounds_with_2_kills"),
            "k3": p.get("rounds_with_3_kills"),
            "k4": p.get("rounds_with_4_kills"),
            "k5": p.get("rounds_with_5_kills"),
        })

    # Formater kamper
    match_list = []
    for m in raw_matches:
        teams = m.get("teams", [])
        opponent = next((t.get("name", "Ukjent") for t in teams if t.get("id") != TEAM_ID), "Ukjent")
        vepsene_score = next((t.get("score") for t in teams if t.get("id") == TEAM_ID), None)
        opp_score = next((t.get("score") for t in teams if t.get("id") != TEAM_ID), None)
        match_list.append({
            "date": m.get("scheduled_at", "")[:10],
            "opponent": opponent,
            "score_us": vepsene_score,
            "score_them": opp_score,
            "status": m.get("status", ""),
        })

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "competition": comp_name,
        "players": player_list,
        "matches": match_list,
    }

    out_path = Path(__file__).parent / "stats.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLagret: {out_path}")
    print(f"Spillere: {len(player_list)}, Kamper: {len(match_list)}")


if __name__ == "__main__":
    main()
