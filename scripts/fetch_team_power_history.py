"""
Puissance d'équipe /110 (notes Sofascore) par saison et par équipe, sur plusieurs saisons,
pour tester si la puissance de la saison précédente aide la prédiction (feature sans fuite).

Sortie : data/team_power_history.json = { "20/21": {team_norm: power, ...}, ... }.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import ScraperFC as sfc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "team_power_history.json"
SEASONS = ["19/20", "20/21", "21/22", "22/23", "23/24", "24/25", "25/26"]
LEAGUES = ["England Premier League", "Spain La Liga", "Italy Serie A",
           "Germany Bundesliga", "France Ligue 1"]
MIN_APPS, XI = 5, 11


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def main() -> int:
    ss = sfc.Sofascore()
    history: dict[str, dict[str, float]] = {}
    for season in SEASONS:
        season_map: dict[str, float] = {}
        for league in LEAGUES:
            try:
                df = ss.scrape_player_league_stats(season, league)
            except Exception as exc:  # noqa: BLE001
                print(f"  {season} {league}: {type(exc).__name__}")
                continue
            df = df[pd.to_numeric(df.get("appearances"), errors="coerce").fillna(0) >= MIN_APPS]
            for team, grp in df.groupby("team"):
                core = grp.sort_values("minutesPlayed", ascending=False).head(XI)
                season_map[norm(team)] = round(float(pd.to_numeric(core["rating"], errors="coerce").fillna(0).sum()), 1)
        history[season] = season_map
        print(f"  {season}: {len(season_map)} équipes")
    OUT.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"écrit {OUT.name} ({len(history)} saisons)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
