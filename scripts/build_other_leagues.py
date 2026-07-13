"""Build descriptive statistics for non-Big-Five football leagues.

The export contains both an all-period compatible ``leagues`` key and a ``seasons``
map used by the site season filter.
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
BIG5 = {"E0", "SP1", "I1", "D1", "F1"}

DIV = {
    "E0": ("Angleterre - Premier League", "GB"), "E1": ("Angleterre - Championship", "GB"),
    "E2": ("Angleterre - League One", "GB"), "E3": ("Angleterre - League Two", "GB"),
    "EC": ("Angleterre - National League", "GB"), "SC0": ("Ecosse - Premiership", "GB-SCT"),
    "SC1": ("Ecosse - Championship", "GB-SCT"), "SC2": ("Ecosse - League One", "GB-SCT"),
    "SC3": ("Ecosse - League Two", "GB-SCT"), "D1": ("Allemagne - Bundesliga", "DE"),
    "D2": ("Allemagne - 2. Bundesliga", "DE"), "I1": ("Italie - Serie A", "IT"),
    "I2": ("Italie - Serie B", "IT"), "SP1": ("Espagne - LaLiga", "ES"),
    "SP2": ("Espagne - LaLiga 2", "ES"), "F1": ("France - Ligue 1", "FR"),
    "F2": ("France - Ligue 2", "FR"), "N1": ("Pays-Bas - Eredivisie", "NL"),
    "B1": ("Belgique - Pro League", "BE"), "P1": ("Portugal - Primeira Liga", "PT"),
    "T1": ("Turquie - Super Lig", "TR"), "G1": ("Grece - Super League", "GR"),
    "ARG": ("Argentine - Primera", "AR"), "AUT": ("Autriche - Bundesliga", "AT"),
    "BRA": ("Bresil - Serie A", "BR"), "CHN": ("Chine - Super League", "CN"),
    "DEN": ("Danemark - Superliga", "DK"), "FIN": ("Finlande - Veikkausliiga", "FI"),
    "IRL": ("Irlande - Premier Division", "IE"), "JAP": ("Japon - J1 League", "JP"),
    "MEX": ("Mexique - Liga MX", "MX"), "NOR": ("Norvege - Eliteserien", "NO"),
    "POL": ("Pologne - Ekstraklasa", "PL"), "ROM": ("Roumanie - Liga I", "RO"),
    "RUS": ("Russie - Premier League", "RU"), "SUI": ("Suisse - Super League", "CH"),
    "SWE": ("Suede - Allsvenskan", "SE"), "USA": ("Etats-Unis - MLS", "US"),
}


def _pct(mask) -> float:
    return round(100 * float(mask.mean()), 1)


def season_label(value) -> str:
    dt = pd.to_datetime(value)
    return f"{dt.year}-{dt.year + 1}" if dt.month >= 8 else f"{dt.year - 1}-{dt.year}"


def build_rows(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for code, group in frame.groupby("Division"):
        name, flag = DIV.get(str(code), (str(code), ""))
        rows.append({
            "code": str(code),
            "name": name,
            "flag": flag,
            "matches": int(len(group)),
            "goals_per_match": round(float(group["goals"].mean()), 2),
            "home_pct": _pct(group["FTResult"] == "H"),
            "draw_pct": _pct(group["FTResult"] == "D"),
            "away_pct": _pct(group["FTResult"] == "A"),
            "over25_pct": _pct(group["goals"] > 2.5),
            "corners_per_match": round(float(group["corners"].mean()), 1) if group["corners"].notna().any() else None,
            "cards_per_match": round(float(group["cards"].mean()), 1) if group["cards"].notna().any() else None,
            "shots_per_match": round(float(group["shots"].mean()), 1) if group["shots"].notna().any() else None,
        })
    rows.sort(key=lambda row: row["goals_per_match"], reverse=True)
    return rows


def main() -> int:
    cols = [
        "Division", "MatchDate", "FTHome", "FTAway", "FTResult",
        "HomeCorners", "AwayCorners", "HomeYellow", "AwayYellow", "HomeRed", "AwayRed",
        "HomeShots", "AwayShots",
    ]
    df = pd.read_csv(SRC, usecols=cols)
    df = df[(df["MatchDate"] >= SINCE) & (~df["Division"].isin(BIG5))]
    df = df.dropna(subset=["FTHome", "FTAway", "FTResult"]).copy()
    df["season"] = df["MatchDate"].apply(season_label)
    df["goals"] = df["FTHome"] + df["FTAway"]
    df["corners"] = df["HomeCorners"] + df["AwayCorners"]
    df["cards"] = df[["HomeYellow", "AwayYellow", "HomeRed", "AwayRed"]].sum(axis=1)
    df["shots"] = df["HomeShots"] + df["AwayShots"]

    seasons = {}
    for season, group in df.groupby("season"):
        rows = build_rows(group)
        if rows:
            seasons[str(season)] = rows
    latest = sorted(seasons)[-1] if seasons else None
    rows = seasons.get(latest, build_rows(df))
    payload = {
        "source": "club-football-match-data, since 2019",
        "note": "Descriptive per-league statistics: outcomes, goals, cards and rhythm.",
        "season_default": latest,
        "seasons": seasons,
        "leagues": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} leagues, {len(seasons)} seasons -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
