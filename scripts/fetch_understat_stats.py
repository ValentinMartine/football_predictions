"""
Récupère les statistiques joueurs et équipes des 5 grands championnats (Understat via
soccerdata) et produit data/understat_stats.json pour l'onglet Statistiques du site.

Joueurs : buts, passes décisives, xG, xA, minutes. Équipes : buts pour/contre, xG/xGA.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import soccerdata as sd

OUT = Path(__file__).resolve().parents[1] / "data" / "understat_stats.json"
LEAGUES = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A", "GER-Bundesliga", "FRA-Ligue 1"]
SEASON = "2025"           # saison 2025-2026
TOP_N = 25


def _records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        rec = {}
        for c in cols:
            v = r[c]
            rec[c] = round(float(v), 2) if isinstance(v, float) else (int(v) if isinstance(v, (int,)) else str(v))
        out.append(rec)
    return out


def main() -> None:
    us = sd.Understat(leagues=LEAGUES, seasons=SEASON)

    ps = us.read_player_season_stats().reset_index()
    ps = ps[ps["minutes"] >= 500]  # filtre bruit (joueurs à faible temps de jeu)
    ps["league"] = ps["league"].astype(str)
    pcols = ["player", "team", "league", "matches", "minutes", "goals", "assists", "xg", "xa"]

    top_scorers = _records(ps.sort_values("goals", ascending=False).head(TOP_N), pcols)
    top_assists = _records(ps.sort_values("assists", ascending=False).head(TOP_N), pcols)
    top_xg = _records(ps.sort_values("xg", ascending=False).head(TOP_N), pcols)
    top_xa = _records(ps.sort_values("xa", ascending=False).head(TOP_N), pcols)

    # Équipes : format long (une ligne par équipe et par match) → buts/xG pour et contre
    tm = us.read_team_match_stats().reset_index()
    home = tm[["league", "home_team", "home_goals", "home_xg", "away_goals", "away_xg"]].rename(
        columns={"home_team": "team", "home_goals": "gf", "home_xg": "xgf",
                 "away_goals": "ga", "away_xg": "xga"})
    away = tm[["league", "away_team", "away_goals", "away_xg", "home_goals", "home_xg"]].rename(
        columns={"away_team": "team", "away_goals": "gf", "away_xg": "xgf",
                 "home_goals": "ga", "home_xg": "xga"})
    long = pd.concat([home, away], ignore_index=True)
    agg = long.groupby(["league", "team"]).agg(
        matches=("gf", "size"), gf=("gf", "sum"), ga=("ga", "sum"),
        xgf=("xgf", "sum"), xga=("xga", "sum"),
    ).reset_index()
    agg["xg_diff"] = agg["xgf"] - agg["xga"]
    teams = _records(agg.sort_values("xg_diff", ascending=False),
                     ["team", "league", "matches", "gf", "ga", "xgf", "xga", "xg_diff"])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": "2025-2026",
        "source": "Understat (via soccerdata)",
        "n_players": int(len(ps)),
        "top_scorers": top_scorers,
        "top_assists": top_assists,
        "top_xg": top_xg,
        "top_xa": top_xa,
        "teams": teams,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit : {OUT} ({len(ps)} joueurs, {len(teams)} équipes)")
    print("Top buteur:", top_scorers[0]["player"], top_scorers[0]["goals"], "buts")


if __name__ == "__main__":
    main()
