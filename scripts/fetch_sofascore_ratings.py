"""
Note de puissance d'équipe /110 à partir des notes Sofascore (via ScraperFC).

La note Sofascore /10 est déjà une note multi-critères dépendante du poste. La puissance
d'une équipe = somme des notes des 11 joueurs les plus utilisés (le XI régulier) → /110.
On exporte aussi le détail par joueur (buts, passes, xG, xA, dribbles réussis %, tacles,
passes clés) pour l'affichage sur le site.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import ScraperFC as sfc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "team_power.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/team_power.json")
SEASON = "25/26"
LEAGUES = {
    "England Premier League": "ENG-Premier League",
    "Spain La Liga": "ESP-La Liga",
    "Italy Serie A": "ITA-Serie A",
    "Germany Bundesliga": "GER-Bundesliga",
    "France Ligue 1": "FRA-Ligue 1",
}
MIN_APPS = 5      # bruit : ignorer les joueurs à très peu de matchs notés
XI = 11           # taille du noyau pour la puissance /110


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _f(row, col, default=0.0):
    try:
        v = float(row[col])
        return round(v, 2) if pd.notna(v) else default
    except (KeyError, TypeError, ValueError):
        return default


def main() -> int:
    ss = sfc.Sofascore()
    teams = []
    for sofa_name, league_id in LEAGUES.items():
        try:
            df = ss.scrape_player_league_stats(SEASON, sofa_name)
        except Exception as exc:  # noqa: BLE001
            print(f"  ignoré {sofa_name}: {type(exc).__name__}")
            continue
        df = df[pd.to_numeric(df.get("appearances"), errors="coerce").fillna(0) >= 1]
        for team, grp in df.groupby("team"):
            grp = grp.sort_values("minutesPlayed", ascending=False)

            def rec(r):
                return {
                    "player": str(r["player"]),
                    "rating": _f(r, "rating"),
                    "apps": int(_f(r, "appearances")),
                    "min": int(_f(r, "minutesPlayed")),
                    "g": int(_f(r, "goals")), "a": int(_f(r, "assists")),
                    "xg": _f(r, "expectedGoals"), "xa": _f(r, "expectedAssists"),
                    "drib": _f(r, "successfulDribblesPercentage"),
                    "key_passes": _f(r, "keyPasses"), "tackles": _f(r, "tackles"),
                }

            # Tous les joueurs ayant joué au moins un match, triés par temps de jeu.
            players = [rec(r) for _, r in grp.iterrows()]
            # Puissance /110 = somme des notes du XI le plus utilisé.
            power = round(sum(p["rating"] for p in players[:XI]), 1)
            teams.append({
                "team": str(team), "team_norm": _norm(team), "league": league_id,
                "power": power, "players": players,
            })
        print(f"  {sofa_name}: {df['team'].nunique()} équipes")

    teams.sort(key=lambda t: t["power"], reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": "2025-2026",
        "source": "Sofascore (via ScraperFC)",
        "definition": ("Note Sofascore /10 par joueur (multi-critères, dépendante du poste). "
                       "Puissance d'équipe = somme des notes du XI le plus utilisé (/110)."),
        "teams": teams,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"écrit {len(teams)} équipes -> {OUT.name}")
    if teams:
        print(f"top: {teams[0]['team']} {teams[0]['power']}/110")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
