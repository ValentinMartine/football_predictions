"""Compositions + notes des matchs récents des autres championnats, via Sofascore (ScraperFC).

Pour chaque championnat couvert par Sofascore, récupère les N derniers matchs terminés
de la saison courante avec la composition des deux équipes : poste, buts/passes, xG/xA,
note Sofascore et « ma note » calculée (consciente du poste, comme le reste du projet).

Sortie : data/other_leagues_lineups.json, consommé par l'onglet « Autres championnats ».
Best-effort (scraping) : les ligues en échec sont simplement ignorées.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "other_leagues_lineups.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/other_leagues_lineups.json")
N_MATCHES = 8

# code division (build_other_leagues) -> nom de ligue ScraperFC/Sofascore
LEAGUE_MAP = {
    "E1": "England EFL Championship", "F2": "France Ligue 2", "D2": "Germany 2.Bundesliga",
    "I2": "Italy Serie B", "SP2": "Spain La Liga 2", "N1": "Netherlands Eredivisie",
    "P1": "Portugal Primeira Liga", "T1": "Turkiye Super Lig", "ARG": "Argentina Liga Profesional",
    "MEX": "Mexico Liga MX Apertura", "USA": "USA MLS", "SAU": "Saudi Arabia Pro League",
    "UKR": "Ukraine Premier League",
}
POS_MAP = {"G": "GK", "D": "DC", "M": "MC", "F": "FW"}
POS_GROUP = {"GK": "GK", "DC": "DEF", "MC": "MID", "FW": "ATT"}
POS_ORD = {"GK": 0, "DC": 1, "MC": 2, "FW": 3}


def _f(v, default=0.0):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


def compute_note(group, g, a, xg, xa, conceded):
    off = 1.3 * g + 0.8 * a + 0.5 * xg + 0.5 * xa

    def csb(strong, weak):
        if conceded <= 0:
            return strong
        if conceded == 1:
            return weak
        if conceded == 2:
            return 0.0
        return -0.4 * (conceded - 2)

    if group == "GK":
        note = 6.4 + csb(1.4, 0.6) + 0.5 * off
    elif group == "DEF":
        note = 6.0 + csb(1.1, 0.4) + off
    elif group == "MID":
        note = 6.0 + off + csb(0.3, 0.1)
    else:
        note = 6.0 + off
    return round(min(10.0, max(3.5, note)), 1)


def _div_meta():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bol", ROOT / "scripts" / "build_other_leagues.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DIV


def _players_from_stats(ps, team_home, team_away):
    """Construit les listes home/away depuis le DataFrame player-match Sofascore."""
    home, away = [], []
    for _, r in ps.iterrows():
        mins = int(_f(r.get("minutesPlayed"), 0))
        if mins <= 0:
            continue
        pos = POS_MAP.get(str(r.get("position", "M")), "MC")
        rating = round(_f(r.get("rating"), 6.0), 1)
        pdata = {
            "player": str(r.get("name")),
            "team": str(r.get("teamName")),
            "pos": pos, "display_pos": pos, "ord": POS_ORD.get(pos, 2),
            "g": int(_f(r.get("goals"), 0)), "a": int(_f(r.get("goalAssist"), 0)),
            "xg": round(_f(r.get("expectedGoals"), 0.0), 2),
            "xa": round(_f(r.get("expectedAssists"), 0.0), 2),
            "note": None, "sofa": rating, "_mins": mins,
        }
        (home if pdata["team"] == team_home else away).append(pdata)
    hg = sum(p["g"] for p in home)
    ag = sum(p["g"] for p in away)
    for p in home:
        p["note"] = compute_note(POS_GROUP.get(p["pos"], "ATT"), p["g"], p["a"], p["xg"], p["xa"], ag)
    for p in away:
        p["note"] = compute_note(POS_GROUP.get(p["pos"], "ATT"), p["g"], p["a"], p["xg"], p["xa"], hg)
    for p in home + away:
        p.pop("_mins", None)
    home.sort(key=lambda p: p["ord"])
    away.sort(key=lambda p: p["ord"])
    return home[:18], away[:18]


def main() -> int:
    import ScraperFC as sfc
    sofa = sfc.Sofascore()
    DIV = _div_meta()
    out = {}
    for code, league in LEAGUE_MAP.items():
        name, flag = DIV.get(code, (league, "🏳️"))
        try:
            seasons = sofa.get_valid_seasons(league)
            season = None
            matches = []
            for yr in list(seasons.keys() if isinstance(seasons, dict) else seasons):
                ms = sofa.get_match_dicts(yr, league)
                done = [m for m in ms if m.get("status", {}).get("type") == "finished"]
                if done:
                    season, matches = yr, done
                    break
            if not matches:
                print(f"  {code} {league}: aucun match terminé")
                continue
            matches = sorted(matches, key=lambda m: m.get("startTimestamp", 0))[-N_MATCHES:][::-1]
            league_matches = []
            for m in matches:
                ht = m.get("homeTeam", {}).get("name")
                at = m.get("awayTeam", {}).get("name")
                hs = m.get("homeScore", {}).get("current")
                as_ = m.get("awayScore", {}).get("current")
                try:
                    ps = sofa.scrape_player_match_stats(m["id"])
                except Exception as exc:
                    print(f"    match {m.get('id')} ignoré: {exc}")
                    continue
                home, away = _players_from_stats(ps, ht, at)
                if not home and not away:
                    continue
                date = datetime.fromtimestamp(m.get("startTimestamp", 0), tz=timezone.utc).strftime("%Y-%m-%d")
                league_matches.append({
                    "date": date, "home": ht, "away": at,
                    "score": f"{hs}-{as_}" if hs is not None else None,
                    "home_lineup": home, "away_lineup": away,
                })
            if league_matches:
                out[code] = {"code": code, "name": name, "flag": flag, "season": season, "matches": league_matches}
                print(f"  {code} {league}: {len(league_matches)} matchs avec compos", flush=True)
                _write(out)  # sauvegarde incrémentale : progression conservée si interruption
        except Exception as exc:
            print(f"  {code} {league}: échec ({exc})", flush=True)
            continue

    _write(out)
    total = sum(len(l["matches"]) for l in out.values())
    print(f"Terminé : {len(out)} championnats, {total} matchs avec compos -> {OUT.name}", flush=True)
    return 0


def _write(out: dict) -> None:
    payload = {
        "source": "Sofascore (ScraperFC)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leagues": out,
    }
    blob = json.dumps(payload, ensure_ascii=False, indent=1)
    OUT.write_text(blob, encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(blob, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
