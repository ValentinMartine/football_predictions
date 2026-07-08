"""
Assemble les compositions par match (Understat) et les apparie aux matchs récents des
prédictions, pour l'affichage sur le site.

Lit data/_sched2025.parquet + data/_pm2025.parquet (produits par le fetch), apparie
chaque match récent par date + noms d'équipes normalisés, et écrit lineups.json :
{ "AAAA-MM-JJ|home|away": {home:[joueurs], away:[joueurs]} }
Chaque joueur : nom, minutes, buts, passes déc., xG.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SITE_OUT = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/lineups.json")


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
    sched = pd.read_parquet(ROOT / "data" / "_sched2025.parquet")
    pm = pd.read_parquet(ROOT / "data" / "_pm2025.parquet")
    preds = json.loads((ROOT / "data" / "predictions.json").read_text(encoding="utf-8"))

    gcol = _pick(pm.columns, "game_id", "game")
    pcol = _pick(pm.columns, "player")
    tcol = _pick(pm.columns, "team")
    mcol = _pick(pm.columns, "minutes", "time")
    goal = _pick(pm.columns, "goals")
    ast = _pick(pm.columns, "assists")
    xgc = _pick(pm.columns, "xg")
    sgid = _pick(sched.columns, "game_id", "game")
    sh = _pick(sched.columns, "home_team")
    sa = _pick(sched.columns, "away_team")
    sd_ = _pick(sched.columns, "date")

    sched = sched.copy()
    sched["day"] = pd.to_datetime(sched[sd_]).dt.strftime("%Y-%m-%d")
    # game_id -> (day, home, away)
    game_info = {r[sgid]: (r["day"], r[sh], r[sa]) for _, r in sched.iterrows()}
    # (day, norm home, norm away) -> game_id
    key_to_game = {(r["day"], norm(r[sh]), norm(r[sa])): r[sgid] for _, r in sched.iterrows()}

    def players_for(game_id):
        sub = pm[pm[gcol] == game_id]
        out = []
        for _, r in sub.iterrows():
            out.append({
                "player": str(r[pcol]), "team": str(r[tcol]),
                "min": int(r[mcol]) if pd.notna(r[mcol]) else 0,
                "g": int(r[goal]) if goal and pd.notna(r[goal]) else 0,
                "a": int(r[ast]) if ast and pd.notna(r[ast]) else 0,
                "xg": round(float(r[xgc]), 2) if xgc and pd.notna(r[xgc]) else 0.0,
            })
        return sorted(out, key=lambda x: -x["min"])

    lineups = {}
    matched = 0
    for m in preds["recent_matches"]:
        key = f"{m['date']}|{m['home']}|{m['away']}"
        gid = key_to_game.get((m["date"], norm(m["home"]), norm(m["away"])))
        if gid is None:
            # tolérance ±1 jour + appariement approximatif par jointure de tokens
            for (day, nh, na), g in key_to_game.items():
                if day == m["date"] and (norm(m["home"]) in nh or nh in norm(m["home"])) and (norm(m["away"]) in na or na in norm(m["away"])):
                    gid = g
                    break
        if gid is None:
            continue
        _, hteam, ateam = game_info[gid]
        players = players_for(gid)
        lineups[key] = {
            "home": [p for p in players if p["team"] == hteam][:14],
            "away": [p for p in players if p["team"] == ateam][:14],
        }
        matched += 1

    SITE_OUT.write_text(json.dumps(lineups, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"compos appariées : {matched}/{len(preds['recent_matches'])} matchs -> {SITE_OUT.name}")


if __name__ == "__main__":
    main()
