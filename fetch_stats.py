#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_stats.py — Henter Vepsene-stats fra ggarena.no og lagrer som stats.json
Brukes av GitHub Actions for automatisk oppdatering av nettsiden.

Oppdatert: gamer.no → ggarena.no (mai 2026)
- Ny API-base: https://www.ggarena.no/api/paradise
- Endepunkter bruker /competition/ (singular)
- Ingen cookies nødvendig
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

COMPETITION_URL = "https://www.ggarena.no/competitions/komplettligaen-counter-strike-varen-2026/13835"
TEAM_ID = 84331
SIGNUP_ID = 251830  # Vepsene sin signup_id for denne sesongen
BASE_API = "https://www.ggarena.no/api/paradise"

def _api_url(comp_id, path=""):
    return f"{BASE_API}/competition/{comp_id}{path}"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.5",
    "x-requested-with": "XMLHttpRequest",
})


def api_get(url):
    r = SESSION.get(url, timeout=45)
    r.raise_for_status()
    return r.json()


def get_comp_id():
    m = re.search(r'/(\d+)$', COMPETITION_URL)
    if m:
        return int(m.group(1))
    raise ValueError("Kunne ikke hente competition ID fra URL")


def get_phases(comp_id):
    return api_get(_api_url(comp_id, "/phases?page=1")).get("data", [])


def get_player_stats(comp_id):
    url = _api_url(comp_id, f"/stats/players?paradise_team_id={TEAM_ID}")
    return api_get(url).get("data", [])


def get_matches(comp_id):
    try:
        data = api_get(_api_url(comp_id, f"/matchups?signup_id={SIGNUP_ID}&limit=50"))
        return data.get("data", [])
    except Exception as e:
        print(f"Kunne ikke hente kamper: {e}")
        return []


def main():
    comp_id = get_comp_id()
    print(f"Competition ID: {comp_id}")

    # Hent turneringsinfo
    try:
        comp_data = api_get(_api_url(comp_id))
        comp_name = comp_data.get("competition", {}).get("name", "Komplettligaen")
    except Exception:
        comp_name = "Komplettligaen"
        print("Kunne ikke hente turneringsinfo, bruker standardnavn.")

    # Hent faser
    print("Henter faser...")
    try:
        phases = get_phases(comp_id)
        active = [ph for ph in phases if ph.get("status") in ("started", "finished")]
        chosen = active[-1] if active else (phases[0] if phases else None)
        print(f"  Aktiv fase: {chosen.get('title') if chosen else 'ingen'}")
    except Exception as e:
        print(f"Kunne ikke hente faser: {e}")

    # Hent spillerstatistikk
    print("Henter spillerstatistikk...")
    players = get_player_stats(comp_id)
    print(f"  {len(players)} spillere funnet")

    # Hent kamper
    print("Henter kamper...")
    raw_matches = get_matches(comp_id)

    # Formater spillerdata
    player_list = []
    for p in sorted(players, key=lambda x: float(x.get("rating") or 0), reverse=True):
        hs = p.get("headshot_ratio")
        player_list.append({
            "name": p.get("player_name") or p.get("user", {}).get("user_name", "Ukjent"),
            "rating": round(float(p.get("rating") or 0), 2),
            "kills": p.get("kills"),
            "assists": p.get("assists"),
            "deaths": p.get("deaths"),
            "kd_diff": p.get("kd_diff"),
            "adr": None,  # Ikke tilgjengelig i ny API
            "hs_pct": round(float(hs) * 100, 1) if hs is not None else None,
            "entry_kills": p.get("firstkills"),
            "clutches": p.get("clutches_won"),
            "maps_played": p.get("maps_played"),
            "k2": None,  # Ikke tilgjengelig i ny API
            "k3": None,
            "k4": None,
            "k5": None,
        })

    # Formater kamper
    match_list = []
    for m in raw_matches:
        home_signup = m.get("home_signup", {})
        away_signup = m.get("away_signup", {})
        home_team = home_signup.get("team", {})

        is_home = home_team.get("id") == TEAM_ID
        opponent = away_signup.get("name", "Ukjent") if is_home else home_signup.get("name", "Ukjent")

        home_score = m.get("home_score")
        away_score = m.get("away_score")
        score_us = home_score if is_home else away_score
        score_them = away_score if is_home else home_score

        winning_side = m.get("winning_side")
        won = None
        if winning_side:
            won = (winning_side == "home") == is_home

        match_list.append({
            "date": (m.get("start_time") or "")[:10],
            "opponent": opponent,
            "score_us": score_us,
            "score_them": score_them,
            "status": winning_side or "",
            "won": won,
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
