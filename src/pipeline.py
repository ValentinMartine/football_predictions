from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

from src.elo import ClubElo, expected_score

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
FORM_WINDOWS = (5, 10)
LEAGUE_NAMES = {
    "E0": "Premier League",
    "SP1": "La Liga",
    "I1": "Serie A",
    "D1": "Bundesliga",
    "F1": "Ligue 1",
}
LEAGUE_IDS = {code: i for i, code in enumerate(LEAGUE_NAMES)}


def _read_one(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]).copy()
    season, league = path.stem.split("_", 1)
    df["season"] = season
    df["league"] = league
    df["date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce", format="mixed")
    df = df.dropna(subset=["date"])
    return df


def load_matches() -> pd.DataFrame:
    frames = [_read_one(path) for path in sorted(RAW.glob("*.csv"))]
    if not frames:
        raise FileNotFoundError(f"Aucun CSV football-data dans {RAW}")
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["date", "league", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
    return df


def _points(gf: int, ga: int) -> int:
    return 3 if gf > ga else (1 if gf == ga else 0)


def _odds(row, side: str) -> float | None:
    candidates = [
        f"B365C{side}", f"PSCH" if side == "H" else f"PSC{side}",
        f"AvgC{side}", f"MaxC{side}",
        f"B365{side}", f"PS{side}", f"Avg{side}", f"Max{side}",
    ]
    for col in candidates:
        if col in row.index:
            try:
                value = float(row[col])
            except (TypeError, ValueError):
                continue
            if value > 1:
                return value
    return None


def build_features() -> pd.DataFrame:
    df = load_matches()
    elo_by_league: dict[str, ClubElo] = defaultdict(ClubElo)
    histories: dict[tuple[str, str], deque] = {
        (league, team): deque(maxlen=max(FORM_WINDOWS))
        for league in LEAGUE_NAMES for team in []
    }
    histories = defaultdict(lambda: deque(maxlen=max(FORM_WINDOWS)))
    last_date: dict[tuple[str, str], pd.Timestamp] = {}
    rows = []

    for row in df.itertuples(index=False):
        r = pd.Series(row._asdict())
        league = str(r["league"])
        home, away = str(r["HomeTeam"]), str(r["AwayTeam"])
        hg, ag = int(r["FTHG"]), int(r["FTAG"])
        key_h, key_a = (league, home), (league, away)

        elo = elo_by_league[league]
        elo_home, elo_away, elo_diff = elo.pre_match(home, away)

        odds_home = _odds(r, "H")
        odds_draw = _odds(r, "D")
        odds_away = _odds(r, "A")
        if odds_home and odds_draw and odds_away:
            raw_home, raw_draw, raw_away = 1 / odds_home, 1 / odds_draw, 1 / odds_away
            overround = raw_home + raw_draw + raw_away
            imp_home, imp_draw, imp_away = raw_home / overround, raw_draw / overround, raw_away / overround
        else:
            overround = 1.06
            imp_home = imp_draw = imp_away = 1 / 3

        features = {
            "date": r["date"],
            "season": r["season"],
            "league": league,
            "league_name": LEAGUE_NAMES.get(league, league),
            "league_id": LEAGUE_IDS.get(league, -1),
            "home_team": home,
            "away_team": away,
            "home_goals": hg,
            "away_goals": ag,
            "outcome": 0 if hg > ag else (1 if hg == ag else 2),
            "elo_home": elo_home,
            "elo_away": elo_away,
            "elo_diff": elo_diff,
            "rest_home": min((r["date"] - last_date[key_h]).days, 30) if key_h in last_date else 14,
            "rest_away": min((r["date"] - last_date[key_a]).days, 30) if key_a in last_date else 14,
            "odds_home": odds_home,
            "odds_draw": odds_draw,
            "odds_away": odds_away,
            "market_home": imp_home,
            "market_draw": imp_draw,
            "market_away": imp_away,
            "market_home_minus_elo": imp_home - expected_score(elo_home, elo_away),
            "overround": overround,
        }

        for window in FORM_WINDOWS:
            for side, key in (("home", key_h), ("away", key_a)):
                recent = list(histories[key])[-window:]
                if recent:
                    pts = np.mean([x["pts"] for x in recent])
                    gf = np.mean([x["gf"] for x in recent])
                    ga = np.mean([x["ga"] for x in recent])
                    shots = np.mean([x["shots"] for x in recent])
                    shots_target = np.mean([x["shots_target"] for x in recent])
                else:
                    pts, gf, ga, shots, shots_target = 1.2, 1.3, 1.3, 11.0, 4.0
                features[f"form_{side}_{window}"] = pts
                features[f"gf_{side}_{window}"] = gf
                features[f"ga_{side}_{window}"] = ga
                features[f"shots_{side}_{window}"] = shots
                features[f"st_{side}_{window}"] = shots_target

            features[f"form_diff_{window}"] = features[f"form_home_{window}"] - features[f"form_away_{window}"]
            features[f"gf_diff_{window}"] = features[f"gf_home_{window}"] - features[f"gf_away_{window}"]
            features[f"ga_diff_{window}"] = features[f"ga_home_{window}"] - features[f"ga_away_{window}"]
            features[f"shots_diff_{window}"] = features[f"shots_home_{window}"] - features[f"shots_away_{window}"]
            features[f"st_diff_{window}"] = features[f"st_home_{window}"] - features[f"st_away_{window}"]

        rows.append(features)

        histories[key_h].append({
            "pts": _points(hg, ag),
            "gf": hg,
            "ga": ag,
            "shots": float(getattr(row, "HS", np.nan) if not pd.isna(getattr(row, "HS", np.nan)) else 11.0),
            "shots_target": float(getattr(row, "HST", np.nan) if not pd.isna(getattr(row, "HST", np.nan)) else 4.0),
        })
        histories[key_a].append({
            "pts": _points(ag, hg),
            "gf": ag,
            "ga": hg,
            "shots": float(getattr(row, "AS", np.nan) if not pd.isna(getattr(row, "AS", np.nan)) else 11.0),
            "shots_target": float(getattr(row, "AST", np.nan) if not pd.isna(getattr(row, "AST", np.nan)) else 4.0),
        })
        last_date[key_h] = last_date[key_a] = r["date"]
        elo.update(home, away, hg, ag)

    return pd.DataFrame(rows)


FEATURE_COLS = [
    "league_id", "elo_home", "elo_away", "elo_diff", "rest_home", "rest_away",
    "market_home", "market_draw", "market_away", "market_home_minus_elo", "overround",
    *[
        f"{prefix}_{side}_{window}"
        for window in FORM_WINDOWS
        for side in ("home", "away")
        for prefix in ("form", "gf", "ga", "shots", "st")
    ],
    *[
        f"{prefix}_diff_{window}"
        for window in FORM_WINDOWS
        for prefix in ("form", "gf", "ga", "shots", "st")
    ],
]


if __name__ == "__main__":
    data = build_features()
    print(data.shape)
    print(data[["date", "league", "home_team", "away_team", "outcome", "odds_home", "odds_draw", "odds_away"]].tail())
