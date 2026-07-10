"""Derniers matchs par championnat (hors Big Five) pour l'onglet « Autres championnats ».

Source : data/european/Matches.csv (club-football-match-data). Pour chaque division,
les N matchs les plus récents avec score, cotes de clôture et une prédiction Elo
rétrospective (probabilités 1/N/2 dérivées de l'écart Elo d'avant-match, avec
avantage du terrain), dans l'esprit rétrospectif du projet.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "european" / "Matches.csv"
OUT = ROOT / "data" / "other_leagues_matches.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/other_leagues_matches.json")
BIG5 = {"E0", "SP1", "I1", "D1", "F1"}
PER_LEAGUE = 20
HFA = 65  # avantage du terrain en points Elo


def _import_div():
    """Réutilise la carte division -> (nom, drapeau) de build_other_leagues."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("bol", ROOT / "scripts" / "build_other_leagues.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DIV


def elo_probs(home_elo, away_elo):
    """Probabilités 1/N/2 depuis l'écart Elo (avantage terrain inclus)."""
    if pd.isna(home_elo) or pd.isna(away_elo):
        return None
    diff = (home_elo + HFA) - away_elo
    p_home_or_draw = 1.0 / (1.0 + 10 ** (-diff / 400))
    p_away_or_draw = 1.0 - p_home_or_draw
    draw = 0.30 * math.exp(-abs(diff) / 300)  # nul plus probable quand les forces sont proches
    p_home = max(p_home_or_draw - draw / 2, 0.01)
    p_away = max(p_away_or_draw - draw / 2, 0.01)
    s = p_home + draw + p_away
    return [round(p_home / s, 3), round(draw / s, 3), round(p_away / s, 3)]


def odds_probs(oh, od, oa):
    """Probabilités implicites 1/N/2 depuis les cotes (marge retirée)."""
    if any(pd.isna(x) or x <= 1 for x in (oh, od, oa)):
        return None
    inv = [1.0 / oh, 1.0 / od, 1.0 / oa]
    s = sum(inv)
    return [round(x / s, 3) for x in inv]


def main() -> int:
    DIV = _import_div()
    cols = ["Division", "MatchDate", "HomeTeam", "AwayTeam", "HomeElo", "AwayElo",
            "FTHome", "FTAway", "FTResult", "OddHome", "OddDraw", "OddAway"]
    df = pd.read_csv(SRC, usecols=cols)
    df = df[~df["Division"].isin(BIG5)].dropna(subset=["HomeTeam", "AwayTeam", "FTResult"])
    df = df.sort_values("MatchDate")

    leagues = []
    for code, g in df.groupby("Division"):
        name, flag = DIV.get(str(code), (str(code), "🏳️"))
        recent = g.tail(PER_LEAGUE).iloc[::-1]
        matches = []
        correct = 0
        graded = 0
        for _, r in recent.iterrows():
            probs = elo_probs(r["HomeElo"], r["AwayElo"])
            source = "elo"
            if not probs:
                probs = odds_probs(r["OddHome"], r["OddDraw"], r["OddAway"])
                source = "market"
            pred = None
            if probs:
                pred = ["H", "D", "A"][max(range(3), key=lambda i: probs[i])]
                graded += 1
                if pred == r["FTResult"]:
                    correct += 1
            matches.append({
                "date": str(r["MatchDate"]),
                "home": r["HomeTeam"], "away": r["AwayTeam"],
                "score": f'{int(r["FTHome"])}-{int(r["FTAway"])}' if pd.notna(r["FTHome"]) else None,
                "result": r["FTResult"],
                "probs": probs, "pred": pred, "prob_source": source if probs else None,
                "odds": [r["OddHome"], r["OddDraw"], r["OddAway"]]
                        if pd.notna(r["OddHome"]) else None,
            })
        leagues.append({
            "code": str(code), "name": name, "flag": flag,
            "hit_rate": round(100 * correct / graded, 1) if graded else None,
            "matches": matches,
        })

    leagues.sort(key=lambda x: x["name"])
    payload = {
        "source": "club-football-match-data",
        "note": "Derniers matchs par championnat, avec prédiction Elo rétrospective (avant-match).",
        "per_league": PER_LEAGUE,
        "leagues": leagues,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(leagues)} championnats, {sum(len(l['matches']) for l in leagues)} matchs -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
