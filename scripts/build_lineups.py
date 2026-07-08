"""
Assemble les compositions par match (Understat) et les apparie aux matchs récents des
prédictions, pour l'affichage sur le site.

Pour chaque match apparié (date + équipes normalisées), on exporte les joueurs des deux
équipes avec : poste, statut (titulaire / entré / sorti), minutes, buts, passes déc., xG.
On désigne aussi l'homme du match (proxy : contribution buts/passes + xG).
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import soccerdata as sd

ROOT = Path(__file__).resolve().parents[1]
SITE_OUT = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/lineups.json")
LEAGUES = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A", "GER-Bundesliga", "FRA-Ligue 1"]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", " ").split())


def _pick(cols, *cands):
    low = {c.lower(): c for c in cols}
    for cand in cands:
        if cand in low:
            return low[cand]
    for c in cols:
        for cand in cands:
            if cand in c.lower():
                return c
    return None


def main() -> None:
    us = sd.Understat(leagues=LEAGUES, seasons="2025")
    sched = us.read_schedule().reset_index()
    pm = us.read_player_match_stats().reset_index()
    preds = json.loads((ROOT / "data" / "predictions.json").read_text(encoding="utf-8"))

    gcol = _pick(pm.columns, "game_id", "game")
    pcol = _pick(pm.columns, "player")
    tcol = _pick(pm.columns, "team")
    poscol = _pick(pm.columns, "position")
    mcol = _pick(pm.columns, "minutes", "time")
    goal = _pick(pm.columns, "goals")
    ast = _pick(pm.columns, "assists")
    xgc = _pick(pm.columns, "xg")
    sgid = _pick(sched.columns, "game_id", "game")
    sh, sa, sdt = _pick(sched.columns, "home_team"), _pick(sched.columns, "away_team"), _pick(sched.columns, "date")

    sched = sched.copy()
    sched["day"] = pd.to_datetime(sched[sdt]).dt.strftime("%Y-%m-%d")
    game_info = {r[sgid]: (r[sh], r[sa]) for _, r in sched.iterrows()}
    key_to_game = {(r["day"], norm(r[sh]), norm(r[sa])): r[sgid] for _, r in sched.iterrows()}

    def players_for(game_id):
        sub = pm[pm[gcol] == game_id]
        out = []
        for _, r in sub.iterrows():
            mins = int(r[mcol]) if pd.notna(r[mcol]) else 0
            if mins <= 0:
                continue
            pos = str(r[poscol]) if poscol and pd.notna(r[poscol]) else ""
            is_sub = pos.lower() == "sub"
            out.append({
                "player": str(r[pcol]), "team": str(r[tcol]),
                "pos": "" if is_sub else pos,
                "on": is_sub,                       # entré en jeu (flèche verte)
                "off": (not is_sub) and mins < 88,  # sorti (flèche rouge)
                "min": mins,
                "g": int(r[goal]) if goal and pd.notna(r[goal]) else 0,
                "a": int(r[ast]) if ast and pd.notna(r[ast]) else 0,
                "xg": round(float(r[xgc]), 2) if xgc and pd.notna(r[xgc]) else 0.0,
            })
        # titulaires d'abord (par minutes), puis remplaçants
        return sorted(out, key=lambda x: (x["on"], -x["min"]))

    def find_game(m):
        gid = key_to_game.get((m["date"], norm(m["home"]), norm(m["away"])))
        if gid is not None:
            return gid
        for (day, nh, na), g in key_to_game.items():
            if day == m["date"] and (norm(m["home"]) in nh or nh in norm(m["home"])) \
               and (norm(m["away"]) in na or na in norm(m["away"])):
                return g
        return None

    lineups, matched = {}, 0
    for m in preds["recent_matches"]:
        gid = find_game(m)
        if gid is None:
            continue
        hteam, ateam = game_info[gid]
        players = players_for(gid)
        if not players:
            continue
        # homme du match : meilleure contribution (buts x3 + passes x2 + xG)
        motm = max(players, key=lambda p: p["g"] * 3 + p["a"] * 2 + p["xg"])
        for p in players:
            p["motm"] = (p["player"] == motm["player"] and p["team"] == motm["team"])
        lineups[f"{m['date']}|{m['home']}|{m['away']}"] = {
            "home": [p for p in players if p["team"] == hteam][:16],
            "away": [p for p in players if p["team"] == ateam][:16],
        }
        matched += 1

    SITE_OUT.write_text(json.dumps(lineups, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"compos appariées : {matched}/{len(preds['recent_matches'])} matchs -> {SITE_OUT.name}")


if __name__ == "__main__":
    main()
