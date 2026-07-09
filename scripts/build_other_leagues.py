"""
Statistiques descriptives par championnat (38 divisions, dataset club-football-match-data),
pour l'onglet « Autres championnats » du site. Fenêtre récente (depuis 2019).

Par division : nb de matchs, buts/match, % domicile/nul/extérieur, % plus de 2,5 buts,
corners/match, cartons/match, tirs/match. Avec nom lisible et drapeau du pays.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "european" / "Matches.csv"
OUT = ROOT / "data" / "other_leagues.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/other_leagues.json")
SINCE = "2019-01-01"

# code division -> (nom, drapeau)
DIV = {
    "E0": ("Angleterre - Premier League", "🇬🇧"), "E1": ("Angleterre - Championship", "🇬🇧"),
    "E2": ("Angleterre - League One", "🇬🇧"), "E3": ("Angleterre - League Two", "🇬🇧"),
    "EC": ("Angleterre - National League", "🇬🇧"), "SC0": ("Écosse - Premiership", "🏴"),
    "SC1": ("Écosse - Championship", "🏴"), "SC2": ("Écosse - League One", "🏴"),
    "SC3": ("Écosse - League Two", "🏴"), "D1": ("Allemagne - Bundesliga", "🇩🇪"),
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


def _pct(mask) -> float:
    return round(100 * float(mask.mean()), 1)


def main() -> int:
    cols = ["Division", "MatchDate", "FTHome", "FTAway", "FTResult",
            "HomeCorners", "AwayCorners", "HomeYellow", "AwayYellow", "HomeRed", "AwayRed",
            "HomeShots", "AwayShots"]
    df = pd.read_csv(SRC, usecols=cols)
    df = df[df["MatchDate"] >= SINCE].dropna(subset=["FTHome", "FTAway", "FTResult"])
    df["goals"] = df["FTHome"] + df["FTAway"]
    df["corners"] = df["HomeCorners"] + df["AwayCorners"]
    df["cards"] = df[["HomeYellow", "AwayYellow", "HomeRed", "AwayRed"]].sum(axis=1)
    df["shots"] = df["HomeShots"] + df["AwayShots"]

    rows = []
    for code, g in df.groupby("Division"):
        name, flag = DIV.get(str(code), (str(code), "🏳️"))
        rows.append({
            "code": str(code), "name": name, "flag": flag,
            "matches": int(len(g)),
            "goals_per_match": round(float(g["goals"].mean()), 2),
            "home_pct": _pct(g["FTResult"] == "H"),
            "draw_pct": _pct(g["FTResult"] == "D"),
            "away_pct": _pct(g["FTResult"] == "A"),
            "over25_pct": _pct(g["goals"] > 2.5),
            "corners_per_match": round(float(g["corners"].mean()), 1) if g["corners"].notna().any() else None,
            "cards_per_match": round(float(g["cards"].mean()), 1) if g["cards"].notna().any() else None,
            "shots_per_match": round(float(g["shots"].mean()), 1) if g["shots"].notna().any() else None,
        })
    rows.sort(key=lambda r: r["goals_per_match"], reverse=True)
    payload = {
        "source": "club-football-match-data (Kaggle), depuis 2019",
        "note": "Statistiques descriptives par championnat : rythme de jeu, issues, buts, cartons.",
        "leagues": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} championnats -> {OUT.name}")
    print("plus de buts:", rows[0]["name"], rows[0]["goals_per_match"], "| moins:", rows[-1]["name"], rows[-1]["goals_per_match"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
