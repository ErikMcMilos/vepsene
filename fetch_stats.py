#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_stats.py — Henter Vepsene-stats fra ggarena.no og lagrer som stats.json
Brukes av GitHub Actions for automatisk oppdatering av nettsiden.

Krever GGARENA_COOKIE environment variable for utvidede stats (ADR, damage, 2K-5K m.m.).
Faller tilbake til grunnleggende stats uten cookie.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

COMPETITION_URL = "https://www.ggarena.no/competitions/komplettligaen-counter-strike-varen-2026/13835"
TEAM_ID = 84331
SIGNUP_ID = 251830
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


def load_cookie_from_env():
    cookie = os.environ.get("GGARENA_COOKIE", "").strip()
    xsrf = os.environ.get("GGARENA_XSRF", "").strip()
    if cookie:
        SESSION.headers["cookie"] = cookie
        print("  Bruker GGARENA_COOKIE for autentisering")
    if xsrf:
        SESSION.headers["x-xsrf-token"] = xsrf
    return bool(cookie)


def api_get(url):
    r = SESSION.get(url, timeout=45)
    r.raise_for_status()
    return r.json()


def get_comp_id():
    m = re.search(r'/(\d+)$', COMPETITION_URL)
    if m:
        return int(m.group(1))
    raise ValueError("Kunne ikke hente competition ID fra URL")


def get_player_stats(comp_id, use_extended):
    if use_extended:
        try:
            url = _api_url(comp_id, f"/stats/players/extended?paradise_team_id={TEAM_ID}")
            data = api_get(url).get("data", [])
            if data:
                print("  Bruker extended stats (ADR, damage, 2K-5K m.m.)")
                return data, True
        except Exception as e:
            print(f"  Extended stats feilet ({e}), faller tilbake til basis")
    url = _api_url(comp_id, f"/stats/players?paradise_team_id={TEAM_ID}")
    return api_get(url).get("data", []), False


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

    has_cookie = load_cookie_from_env()

    try:
        comp_data = api_get(_api_url(comp_id))
        comp_name = comp_data.get("competition", {}).get("name", "Komplettligaen")
    except Exception:
        comp_name = "Komplettligaen"
        print("Kunne ikke hente turneringsinfo, bruker standardnavn.")

    print("Henter spillerstatistikk...")
    players, is_extended = get_player_stats(comp_id, has_cookie)
    print(f"  {len(players)} spillere funnet")

    print("Henter kamper...")
    raw_matches = get_matches(comp_id)
    print(f"  {len(raw_matches)} kamper funnet")

    player_list = []
    for p in sorted(players, key=lambda x: float(x.get("rating") or 0), reverse=True):
        hs = p.get("headshot_ratio")
        traded_ratio = p.get("traded_deaths_ratio")
        entry = p.get("firstkills") if is_extended else p.get("firstkills")
        player_list.append({
            "name": p.get("player_name") or p.get("user", {}).get("user_name", "Ukjent"),
            "rating": round(float(p.get("rating") or 0), 2),
            "kills": p.get("kills"),
            "assists": p.get("assists"),
            "deaths": p.get("deaths"),
            "kd_diff": p.get("kd_diff"),
            "maps_played": p.get("maps_played"),
            "rounds_played": p.get("rounds_played") if is_extended else None,
            "damage": p.get("damage_given") if is_extended else None,
            "adr": round(float(p.get("damage_per_round")), 0) if is_extended and p.get("damage_per_round") is not None else None,
            "hs_pct": round(float(hs) * 100, 1) if hs is not None else None,
            "entry_kills": entry,
            "clutches": p.get("clutches_won"),
            "trades": p.get("trade_kills") if is_extended else None,
            "traded_pct": round(float(traded_ratio) * 100, 1) if is_extended and traded_ratio is not None else None,
            "k2": p.get("rounds_with_2_kills") if is_extended else None,
            "k3": p.get("rounds_with_3_kills") if is_extended else None,
            "k4": p.get("rounds_with_4_kills") if is_extended else None,
            "k5": p.get("rounds_with_5_kills") if is_extended else None,
            "kast": round(float(p.get("kast_ratio")) * 100, 1) if is_extended and p.get("kast_ratio") is not None else None,
        })

    match_list = []
    for m in sorted(raw_matches, key=lambda x: x.get("start_time") or ""):
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
            "home": is_home,
            "score_us": score_us,
            "score_them": score_them,
            "won": won,
        })

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "competition": comp_name,
        "extended": is_extended,
        "players": player_list,
        "matches": match_list,
    }

    out_path = Path(__file__).parent / "stats.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLagret: {out_path}")
    print(f"Spillere: {len(player_list)}, Kamper: {len(match_list)}, Extended: {is_extended}")


if __name__ == "__main__":
    main()
