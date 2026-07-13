"""Build recent non-Big-Five matches with retrospective Elo predictions.

The output keeps a compact recent-match view, but now includes enough matches per
season for the site season filter.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "european" / "Matches.csv"
OUT = ROOT / "data" / "other_leagues_matches.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/other_leagues_matches.json")
BIG5 = {"E0", "SP1", "I1", "D1", "F1"}
PER_LEAGUE_SEASON = 20
HFA = 65


def _import_div():
    spec = importlib.util.spec_from_file_location("bol", ROOT / "scripts" / "build_other_leagues.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DIV


def season_label(value) -> str:
    dt = pd.to_datetime(value)
    return f"{dt.year}-{dt.year + 1}" if dt.month >= 8 else f"{dt.year - 1}-{dt.year}"


def elo_probs(home_elo, away_elo):
    if pd.isna(home_elo) or pd.isna(away_elo):
        return None
    diff = (home_elo + HFA) - away_elo
    p_home_or_draw = 1.0 / (1.0 + 10 ** (-diff / 400))
    p_away_or_draw = 1.0 - p_home_or_draw
    draw = 0.30 * math.exp(-abs(diff) / 300)
    p_home = max(p_home_or_draw - draw / 2, 0.01)
    p_away = max(p_away_or_draw - draw / 2, 0.01)
    total = p_home + draw + p_away
    return [round(p_home / total, 3), round(draw / total, 3), round(p_away / total, 3)]


def odds_probs(oh, od, oa):
    if any(pd.isna(x) or x <= 1 for x in (oh, od, oa)):
        return None
    inv = [1.0 / oh, 1.0 / od, 1.0 / oa]
    total = sum(inv)
    return [round(x / total, 3) for x in inv]


def main() -> int:
    div_meta = _import_div()
    cols = [
        "Division", "MatchDate", "HomeTeam", "AwayTeam", "HomeElo", "AwayElo",
        "FTHome", "FTAway", "FTResult", "OddHome", "OddDraw", "OddAway",
    ]
    df = pd.read_csv(SRC, usecols=cols)
    df = df[~df["Division"].isin(BIG5)].dropna(subset=["HomeTeam", "AwayTeam", "FTResult"]).copy()
    df["season"] = df["MatchDate"].apply(season_label)
    df = df.sort_values("MatchDate")

    leagues = []
    for code, league_df in df.groupby("Division"):
        name, flag = div_meta.get(str(code), (str(code), ""))
        recent = (
            league_df.groupby("season", group_keys=False)
            .tail(PER_LEAGUE_SEASON)
            .sort_values("MatchDate", ascending=False)
        )
        matches = []
        correct = 0
        graded = 0
        for _, row in recent.iterrows():
            probs = elo_probs(row["HomeElo"], row["AwayElo"])
            source = "elo"
            if not probs:
                probs = odds_probs(row["OddHome"], row["OddDraw"], row["OddAway"])
                source = "market"
            pred = None
            if probs:
                pred = ["H", "D", "A"][max(range(3), key=lambda idx: probs[idx])]
                graded += 1
                if pred == row["FTResult"]:
                    correct += 1
            matches.append({
                "date": str(row["MatchDate"]),
                "season": str(row["season"]),
                "home": row["HomeTeam"],
                "away": row["AwayTeam"],
                "score": f'{int(row["FTHome"])}-{int(row["FTAway"])}' if pd.notna(row["FTHome"]) else None,
                "result": row["FTResult"],
                "probs": probs,
                "pred": pred,
                "prob_source": source if probs else None,
                "odds": [row["OddHome"], row["OddDraw"], row["OddAway"]] if pd.notna(row["OddHome"]) else None,
            })
        seasons = sorted({m["season"] for m in matches}, reverse=True)
        leagues.append({
            "code": str(code),
            "name": name,
            "flag": flag,
            "seasons": seasons,
            "hit_rate": round(100 * correct / graded, 1) if graded else None,
            "matches": matches,
        })

    leagues.sort(key=lambda item: item["name"])
    all_seasons = sorted({season for league in leagues for season in league["seasons"]}, reverse=True)
    payload = {
        "source": "club-football-match-data",
        "note": "Recent matches by league and season, with retrospective pre-match Elo predictions.",
        "per_league_season": PER_LEAGUE_SEASON,
        "season_default": all_seasons[0] if all_seasons else None,
        "seasons": all_seasons,
        "leagues": leagues,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(leagues)} leagues, {sum(len(l['matches']) for l in leagues)} matches -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
