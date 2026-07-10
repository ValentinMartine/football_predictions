"""
Classements (standings) par championnat et par saison, pour afficher le tableau
final ou en cours en tête des onglets Big Five et Autres championnats.

Source : club-football-match-data (Kaggle). Saisons depuis 2019.
Sortie data/standings.json : { code_division: { "2025-2026": [ {rank, team, played, win, draw, loss, gf, ga, gd, pts} ] } }
avec le nom lisible et le drapeau du championnat.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "european" / "Matches.csv"
OUT = ROOT / "data" / "standings.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/standings.json")
SINCE = "2019-07-01"

# code -> (nom lisible, drapeau) ; Big Five + autres championnats (repris de build_other_leagues / bigfive).
DIV = {
    "E0": ("Angleterre - Premier League", "🇬🇧"), "E1": ("Angleterre - Championship", "🇬🇧"),
    "E2": ("Angleterre - League One", "🇬🇧"), "E3": ("Angleterre - League Two", "🇬🇧"),
    "EC": ("Angleterre - National League", "🇬🇧"), "SC0": ("Écosse - Premiership", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    "SC1": ("Écosse - Championship", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"), "SC2": ("Écosse - League One", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    "SC3": ("Écosse - League Two", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"), "D1": ("Allemagne - Bundesliga", "🇩🇪"),
    "D2": ("Allemagne - 2. Bundesliga", "🇩🇪"), "I1": ("Italie - Serie A", "🇮🇹"),
    "I2": ("Italie - Serie B", "🇮🇹"), "SP1": ("Espagne - LaLiga", "🇪🇸"),
    "SP2": ("Espagne - LaLiga 2", "🇪🇸"), "F1": ("France - Ligue 1", "🇫🇷"),
    "F2": ("France - Ligue 2", "🇫🇷"), "N1": ("Pays-Bas - Eredivisie", "🇳🇱"),
    "B1": ("Belgique - Pro League", "🇧🇪"), "P1": ("Portugal - Primeira Liga", "🇵🇹"),
    "T1": ("Turquie - Süper Lig", "🇹🇷"), "G1": ("Grèce - Super League", "🇬🇷"),
    "ARG": ("Argentine - Primera", "🇦🇷"), "AUT": ("Autriche - Bundesliga", "🇦🇹"),
    "BRA": ("Brésil - Série A", "🇧🇷"), "CHN": ("Chine - Super League", "🇨🇳"),
    "DEN": ("Danemark - Superliga", "🇩🇰"), "FIN": ("Finlande - Veikkausliiga", "🇫🇮"),
    "IRL": ("Irlande - Premier Division", "🇮🇪"), "JAP": ("Japon - J1 League", "🇯🇵"),
    "MEX": ("Mexique - Liga MX", "🇲🇽"), "NOR": ("Norvège - Eliteserien", "🇳🇴"),
    "POL": ("Pologne - Ekstraklasa", "🇵🇱"), "ROM": ("Roumanie - Liga I", "🇷🇴"),
    "RUS": ("Russie - Premier League", "🇷🇺"), "SUI": ("Suisse - Super League", "🇨🇭"),
    "SWE": ("Suède - Allsvenskan", "🇸🇪"), "USA": ("États-Unis - MLS", "🇺🇸"),
}


def season_label(dt: pd.Timestamp) -> str:
    y = dt.year
    start = y if dt.month >= 7 else y - 1
    return f"{start}-{start + 1}"


def main() -> int:
    cols = ["Division", "MatchDate", "HomeTeam", "AwayTeam", "FTHome", "FTAway", "FTResult"]
    df = pd.read_csv(SRC, usecols=cols).dropna(subset=["FTHome", "FTAway", "FTResult", "HomeTeam", "AwayTeam"])
    df = df[df["MatchDate"] >= SINCE].copy()
    df["date"] = pd.to_datetime(df["MatchDate"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["season"] = df["date"].apply(season_label)
    df["FTHome"] = df["FTHome"].astype(int)
    df["FTAway"] = df["FTAway"].astype(int)

    out: dict[str, dict] = {}
    for (div, season), g in df.groupby(["Division", "season"]):
        if str(div) not in DIV:
            continue
        tbl: dict[str, dict] = {}

        def row(team):
            return tbl.setdefault(team, {"team": team, "played": 0, "win": 0, "draw": 0, "loss": 0, "gf": 0, "ga": 0})

        for m in g.itertuples(index=False):
            h, a = row(str(m.HomeTeam)), row(str(m.AwayTeam))
            h["played"] += 1; a["played"] += 1
            h["gf"] += m.FTHome; h["ga"] += m.FTAway
            a["gf"] += m.FTAway; a["ga"] += m.FTHome
            if m.FTResult == "H":
                h["win"] += 1; a["loss"] += 1
            elif m.FTResult == "A":
                a["win"] += 1; h["loss"] += 1
            else:
                h["draw"] += 1; a["draw"] += 1
        rows = list(tbl.values())
        for r in rows:
            r["gd"] = r["gf"] - r["ga"]
            r["pts"] = 3 * r["win"] + r["draw"]
        rows.sort(key=lambda r: (r["pts"], r["gd"], r["gf"]), reverse=True)
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        name, flag = DIV[str(div)]
        out.setdefault(str(div), {"name": name, "flag": flag, "seasons": {}})
        out[str(div)]["seasons"][str(season)] = rows

    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n_seasons = sum(len(v["seasons"]) for v in out.values())
    print(f"{len(out)} championnats, {n_seasons} saisons -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
