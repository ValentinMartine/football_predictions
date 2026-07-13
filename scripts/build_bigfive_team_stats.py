"""Build Big Five team descriptive statistics for the site.

The export keeps the legacy top-level ``teams`` key for compatibility and adds a
``seasons`` map so the UI can filter by season.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "european" / "Matches.csv"
OUT = ROOT / "data" / "bigfive_team_stats.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/bigfive_team_stats.json")
SINCE = "2000-01-01"
MIN_MATCHES = 20

DIV = {
    "E0": ("Premier League", "GB"),
    "SP1": ("LaLiga", "ES"),
    "I1": ("Serie A", "IT"),
    "D1": ("Bundesliga", "DE"),
    "F1": ("Ligue 1", "FR"),
}


def _pct(mask) -> float:
    return round(100 * float(mask.mean()), 1)


def season_label(value) -> str:
    dt = pd.to_datetime(value)
    return f"{dt.year}-{dt.year + 1}" if dt.month >= 8 else f"{dt.year - 1}-{dt.year}"


def build_rows(frame: pd.DataFrame, min_matches: int) -> list[dict]:
    rows = []
    for team, group in frame.groupby("team"):
        n = len(group)
        if n < min_matches:
            continue
        div = group["Division"].mode().iloc[0]
        name, flag = DIV.get(str(div), (str(div), ""))
        points_per_match = (3 * group["win"].sum() + group["draw"].sum()) / n

        def pm(col: str):
            return round(float(group[col].mean()), 2) if group[col].notna().any() else None

        rows.append({
            "team": str(team),
            "league": name,
            "flag": flag,
            "matches": int(n),
            "ppm": round(float(points_per_match), 2),
            "gf_pm": round(float(group["gf"].mean()), 2),
            "ga_pm": round(float(group["ga"].mean()), 2),
            "win_pct": _pct(group["win"] == 1),
            "draw_pct": _pct(group["draw"] == 1),
            "loss_pct": _pct(group["loss"] == 1),
            "over25_pct": _pct(group["total"] > 2.5),
            "shots_pm": pm("shots"),
            "target_pm": pm("target"),
            "corners_pm": pm("corners"),
            "cards_pm": pm("cards"),
            "fouls_pm": pm("fouls"),
        })
    rows.sort(key=lambda row: row["ppm"], reverse=True)
    return rows


def main() -> int:
    cols = [
        "Division", "MatchDate", "HomeTeam", "AwayTeam", "FTHome", "FTAway", "FTResult",
        "HomeShots", "AwayShots", "HomeTarget", "AwayTarget", "HomeCorners", "AwayCorners",
        "HomeYellow", "AwayYellow", "HomeRed", "AwayRed", "HomeFouls", "AwayFouls",
    ]
    df = pd.read_csv(SRC, usecols=cols)
    df = df[(df["MatchDate"] >= SINCE) & (df["Division"].isin(DIV))]
    df = df.dropna(subset=["FTHome", "FTAway", "FTResult"]).copy()
    df["season"] = df["MatchDate"].apply(season_label)

    def side(is_home: bool) -> pd.DataFrame:
        own, opp = ("Home", "Away") if is_home else ("Away", "Home")
        res_win = "H" if is_home else "A"
        res_loss = "A" if is_home else "H"
        out = pd.DataFrame({
            "Division": df["Division"],
            "season": df["season"],
            "team": df[f"{own}Team"],
            "gf": df[f"FT{own}"],
            "ga": df[f"FT{opp}"],
            "shots": df[f"{own}Shots"],
            "target": df[f"{own}Target"],
            "corners": df[f"{own}Corners"],
            "cards": df[f"{own}Yellow"].fillna(0) + df[f"{own}Red"].fillna(0),
            "fouls": df[f"{own}Fouls"],
            "total": df["FTHome"] + df["FTAway"],
        })
        out["win"] = (df["FTResult"] == res_win).astype(int)
        out["draw"] = (df["FTResult"] == "D").astype(int)
        out["loss"] = (df["FTResult"] == res_loss).astype(int)
        return out

    long = pd.concat([side(True), side(False)], ignore_index=True)
    seasons = {}
    for season, group in long.groupby("season"):
        rows = build_rows(group, min_matches=5)
        if rows:
            seasons[str(season)] = rows
    latest = sorted(seasons)[-1] if seasons else None
    rows = seasons.get(latest, build_rows(long, MIN_MATCHES))

    payload = {
        "source": "club-football-match-data, since 2000",
        "note": "Per-team Big Five statistics. Headers are sortable on the site.",
        "min_matches": MIN_MATCHES,
        "season_default": latest,
        "seasons": seasons,
        "teams": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} teams, {len(seasons)} seasons -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
