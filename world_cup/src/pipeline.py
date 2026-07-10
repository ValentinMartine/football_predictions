"""
Chronological feature construction for international football.

Every row stores the state before the match, so features are usable without
information leakage.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.football_elo import FootballElo, k_for_tournament

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "results.csv"
RANKINGS = ROOT / "data" / "fifa_rankings.csv"
TEAMS_METADATA = ROOT / "data" / "worldcup_teams.csv"
WORLD_CUP_MATCHES = ROOT / "data" / "worldcup_matches.csv"
FORM_WINDOWS = (5, 10, 20)
CONFEDERATIONS = ("AFC", "CAF", "CONCACAF", "CONMEBOL", "OFC", "UEFA")
STAGES = ("group", "round_of_32", "round_of_16", "quarter_final", "semi_final", "third_place", "final")
HOST_2026_COUNTRIES = ("Canada", "Mexico", "United States")
HOST_2026_CITIES = {
    "Arlington": "arlington",
    "Atlanta": "atlanta",
    "Dallas": "dallas",
    "East Rutherford": "east_rutherford",
    "Foxborough": "foxborough",
    "Guadalupe": "guadalupe",
    "Houston": "houston",
    "Inglewood": "inglewood",
    "Kansas City": "kansas_city",
    "Mexico City": "mexico_city",
    "Miami Gardens": "miami_gardens",
    "Philadelphia": "philadelphia",
    "Santa Clara": "santa_clara",
    "Seattle": "seattle",
    "Toronto": "toronto",
    "Vancouver": "vancouver",
    "Zapopan": "zapopan",
}

TEAM_ALIASES = {
    "Cape Verde": "Cabo Verde",
    "China": "China PR",
    "DR Congo": "Congo DR",
    "Iran": "IR Iran",
    "Ivory Coast": "Côte d'Ivoire",
    "Kyrgyzstan": "Kyrgyz Republic",
    "North Korea": "Korea DPR",
    "Saint Kitts and Nevis": "St Kitts and Nevis",
    "Saint Lucia": "St Lucia",
    "Saint Vincent and the Grenadines": "St Vincent and the Grenadines",
    "South Korea": "Korea Republic",
    "Taiwan": "Chinese Taipei",
    "United States": "USA",
    "United States Virgin Islands": "US Virgin Islands",
}

CONFED_ALIASES = {}

CONFED_OVERRIDES = {
    "Cabo Verde": "CAF",
    "Cape Verde": "CAF",
    "Congo DR": "CAF",
    "Curaçao": "CONCACAF",
    "Curacao": "CONCACAF",
    "DR Congo": "CAF",
    "Jordan": "AFC",
    "Uzbekistan": "AFC",
}


def _pts(gf: int, ga: int) -> int:
    return 3 if gf > ga else (1 if gf == ga else 0)


def _tournament_context(tournament: str) -> dict[str, int]:
    value = (tournament or "").lower()
    return {
        "is_friendly": int("friendly" in value),
        "is_world_cup": int(value == "fifa world cup"),
        "is_qualifier": int("qualification" in value or "qualifier" in value),
        "is_continental": int(any(x in value for x in [
            "euro", "copa", "african cup", "asian cup", "gold cup", "ofc", "concacaf",
        ])),
        "is_nations_league": int("nations league" in value),
    }


def _load_fifa_index() -> dict[str, dict[str, list]]:
    if not RANKINGS.exists():
        return {}
    rankings = pd.read_csv(RANKINGS)
    rankings = rankings.dropna(subset=["team", "total_points", "date"]).copy()
    rankings["date"] = pd.to_datetime(rankings["date"])
    rankings["rank"] = rankings.groupby("date")["total_points"].rank(method="first", ascending=False)
    rankings = rankings.sort_values(["team", "date"])

    index: dict[str, dict[str, list]] = {}
    for team, group in rankings.groupby("team", sort=False):
        index[str(team)] = {
            "dates": group["date"].tolist(),
            "points": group["total_points"].astype(float).tolist(),
            "ranks": group["rank"].astype(float).tolist(),
        }
    return index


def _load_confederations() -> dict[str, str]:
    index = dict(CONFED_OVERRIDES)
    if not TEAMS_METADATA.exists():
        return index
    teams = pd.read_csv(TEAMS_METADATA)
    teams = teams.dropna(subset=["team_name", "confederation_code"])
    for row in teams.itertuples(index=False):
        index[str(row.team_name)] = str(row.confederation_code)
    return index


def _normalize_stage(stage: str | None) -> str | None:
    value = (stage or "").lower().strip()
    if not value:
        return None
    if "third" in value:
        return "third_place"
    if value == "final":
        return "final"
    if "semi" in value:
        return "semi_final"
    if "quarter" in value:
        return "quarter_final"
    if "round of 32" in value:
        return "round_of_32"
    if "round of 16" in value:
        return "round_of_16"
    if "group" in value or value == "final round":
        return "group"
    return None


def _load_world_cup_stage_index() -> dict[tuple[str, str, str], str]:
    if not WORLD_CUP_MATCHES.exists():
        return {}
    matches = pd.read_csv(WORLD_CUP_MATCHES)
    matches = matches.dropna(subset=["match_date", "home_team_name", "away_team_name", "stage_name"])
    out: dict[tuple[str, str, str], str] = {}
    for row in matches.itertuples(index=False):
        stage = _normalize_stage(row.stage_name)
        if not stage:
            continue
        date = str(row.match_date)
        home = str(row.home_team_name)
        away = str(row.away_team_name)
        out[(date, home, away)] = stage
        out[(date, away, home)] = stage
    return out


def _fifa_before(index: dict[str, dict[str, list]], team: str, date: pd.Timestamp) -> tuple[float, float, int]:
    item = index.get(TEAM_ALIASES.get(team, team))
    if not item:
        return 1300.0, 150.0, 0
    pos = bisect_right(item["dates"], date) - 1
    if pos < 0:
        return 1300.0, 150.0, 0
    return item["points"][pos], item["ranks"][pos], 1


def _team_confederation(index: dict[str, str], team: str) -> str | None:
    key = CONFED_ALIASES.get(team, team)
    return index.get(key) or CONFED_OVERRIDES.get(team)


def _infer_wc26_stage(date: pd.Timestamp) -> str | None:
    if date <= pd.Timestamp("2026-06-26"):
        return "group"
    if pd.Timestamp("2026-06-27") <= date <= pd.Timestamp("2026-07-03"):
        return "round_of_32"
    if pd.Timestamp("2026-07-04") <= date <= pd.Timestamp("2026-07-07"):
        return "round_of_16"
    if pd.Timestamp("2026-07-09") <= date <= pd.Timestamp("2026-07-11"):
        return "quarter_final"
    if pd.Timestamp("2026-07-14") <= date <= pd.Timestamp("2026-07-15"):
        return "semi_final"
    if date == pd.Timestamp("2026-07-18"):
        return "third_place"
    if date == pd.Timestamp("2026-07-19"):
        return "final"
    return None


def _world_cup_stage(index: dict[tuple[str, str, str], str], row) -> str | None:
    if str(row.tournament).lower() != "fifa world cup":
        return None
    if row.date >= pd.Timestamp("2026-06-11"):
        return _infer_wc26_stage(row.date)
    return index.get((row.date.strftime("%Y-%m-%d"), row.home_team, row.away_team))


def build_features(extra_fixtures: pd.DataFrame | None = None) -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["date"] = pd.to_datetime(df["date"])
    df["predict_flag"] = False
    if extra_fixtures is not None and len(extra_fixtures):
        ef = extra_fixtures.copy()
        ef["home_score"] = 0  # scores factices : les features sont pré-match, non utilisées
        ef["away_score"] = 0
        ef["predict_flag"] = True
        ef["date"] = pd.to_datetime(ef["date"])
        df = pd.concat([df, ef], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)

    elo = FootballElo()
    fifa_index = _load_fifa_index()
    confed_index = _load_confederations()
    stage_index = _load_world_cup_stage_index()
    hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=max(FORM_WINDOWS)))
    last_date: dict[str, datetime] = {}
    rows = []

    def form(team: str, window: int) -> tuple[float, float, float]:
        recent = list(hist[team])[-window:]
        if not recent:
            return 1.0, 1.2, 1.2
        pts = sum(x[0] for x in recent) / len(recent)
        gf = sum(x[1] for x in recent) / len(recent)
        ga = sum(x[2] for x in recent) / len(recent)
        return pts, gf, ga

    for r in df.itertuples(index=False):
        home, away = r.home_team, r.away_team
        neutral = bool(r.neutral)
        eh, ea, ediff = elo.pre_match(home, away, neutral)
        rest_h = (r.date - last_date[home]).days if home in last_date else 30
        rest_a = (r.date - last_date[away]).days if away in last_date else 30
        fp_h, fr_h, has_h = _fifa_before(fifa_index, home, r.date)
        fp_a, fr_a, has_a = _fifa_before(fifa_index, away, r.date)
        conf_h = _team_confederation(confed_index, home)
        conf_a = _team_confederation(confed_index, away)
        conf_host = _team_confederation(confed_index, r.country)
        has_confed = int(conf_h is not None and conf_a is not None)
        stage = _world_cup_stage(stage_index, r)
        city_slug = HOST_2026_CITIES.get(str(r.city))

        outcome = 0 if r.home_score > r.away_score else (1 if r.home_score == r.away_score else 2)
        is_wc26 = (r.date >= pd.Timestamp("2026-06-11")) and (str(r.tournament).lower() == "fifa world cup")

        row = {
            "date": r.date,
            "home_team": home,
            "away_team": away,
            "tournament": r.tournament,
            "city": r.city,
            "country": r.country,
            "neutral": int(neutral),
            "elo_home": eh,
            "elo_away": ea,
            "elo_diff": ediff,
            "rest_home": min(rest_h, 60),
            "rest_away": min(rest_a, 60),
            "fifa_points_home": fp_h,
            "fifa_points_away": fp_a,
            "fifa_points_diff": fp_h - fp_a,
            "fifa_rank_home": fr_h,
            "fifa_rank_away": fr_a,
            "fifa_rank_diff": fr_a - fr_h,
            "has_fifa_rank": int(has_h and has_a),
            "has_confederation": has_confed,
            "has_host_confederation": int(conf_host is not None),
            "same_confederation": int(has_confed and conf_h == conf_a),
            "intercontinental_match": int(has_confed and conf_h != conf_a),
            "home_country_match": int(home == r.country),
            "away_country_match": int(away == r.country),
            "home_confed_match_country": int(conf_h is not None and conf_h == conf_host),
            "away_confed_match_country": int(conf_a is not None and conf_a == conf_host),
            "has_world_cup_stage": int(stage is not None),
            "is_world_cup_group_stage": int(stage == "group"),
            "is_world_cup_knockout_stage": int(stage is not None and stage != "group"),
            "match_in_2026_host_country": int(r.country in HOST_2026_COUNTRIES),
            "match_in_2026_host_city": int(city_slug is not None and r.country in HOST_2026_COUNTRIES),
            "tourn_k": k_for_tournament(r.tournament),
            "home_score": r.home_score,
            "away_score": r.away_score,
            "outcome": outcome,
            "is_wc26": is_wc26,
            "is_predict": bool(getattr(r, "predict_flag", False)),
        }
        row.update(_tournament_context(r.tournament))
        for stage_name in STAGES:
            row[f"stage_{stage_name}"] = int(stage == stage_name)
        for confed in CONFEDERATIONS:
            row[f"home_confed_{confed}"] = int(conf_h == confed)
            row[f"away_confed_{confed}"] = int(conf_a == confed)
            row[f"host_confed_{confed}"] = int(conf_host == confed)
        for country in HOST_2026_COUNTRIES:
            key = country.lower().replace(" ", "_")
            row[f"match_country_{key}"] = int(r.country == country)
        for city, slug in HOST_2026_CITIES.items():
            row[f"match_city_{slug}"] = int(r.city == city and r.country in HOST_2026_COUNTRIES)

        for window in FORM_WINDOWS:
            fh, gfh, gah = form(home, window)
            fa, gfa, gaa = form(away, window)
            row.update({
                f"form_home_{window}": fh,
                f"form_away_{window}": fa,
                f"form_diff_{window}": fh - fa,
                f"gf_home_{window}": gfh,
                f"ga_home_{window}": gah,
                f"gf_away_{window}": gfa,
                f"ga_away_{window}": gaa,
                f"gf_diff_{window}": gfh - gfa,
                f"ga_diff_{window}": gah - gaa,
            })
        rows.append(row)

        if getattr(r, "predict_flag", False):
            continue  # match non joué : ne pas polluer l'état (Elo, forme)
        hist[home].append((_pts(r.home_score, r.away_score), r.home_score, r.away_score))
        hist[away].append((_pts(r.away_score, r.home_score), r.away_score, r.home_score))
        last_date[home] = last_date[away] = r.date
        elo.update(home, away, r.home_score, r.away_score, r.tournament, neutral)

    return pd.DataFrame(rows)


CANDIDATE_CONFED_GEO_COLS = [
    "has_confederation", "has_host_confederation", "same_confederation", "intercontinental_match",
    "home_country_match", "away_country_match", "home_confed_match_country", "away_confed_match_country",
    *[
        f"{side}_confed_{confed}"
        for side in ("home", "away", "host")
        for confed in CONFEDERATIONS
    ],
]


CANDIDATE_STAGE_COLS = [
    "has_world_cup_stage", "is_world_cup_group_stage", "is_world_cup_knockout_stage",
    *[f"stage_{stage_name}" for stage_name in STAGES],
]


CANDIDATE_LOCATION_COLS = [
    "match_in_2026_host_country", "match_in_2026_host_city",
    *[f"match_country_{country.lower().replace(' ', '_')}" for country in HOST_2026_COUNTRIES],
    *[f"match_city_{slug}" for slug in HOST_2026_CITIES.values()],
]


FEATURE_COLS = [
    "elo_diff", "elo_home", "elo_away", "neutral",
    "rest_home", "rest_away", "tourn_k",
    "fifa_points_home", "fifa_points_away", "fifa_points_diff",
    "fifa_rank_home", "fifa_rank_away", "fifa_rank_diff", "has_fifa_rank",
    "is_friendly", "is_world_cup", "is_qualifier", "is_continental", "is_nations_league",
    *[
        f"{prefix}_{side}_{window}"
        for window in FORM_WINDOWS
        for side in ("home", "away")
        for prefix in ("form", "gf", "ga")
    ],
    *[
        f"{prefix}_diff_{window}"
        for window in FORM_WINDOWS
        for prefix in ("form", "gf", "ga")
    ],
]


if __name__ == "__main__":
    data = build_features()
    print(data.shape)
    print(data[FEATURE_COLS].describe().round(2).T)
    print("WC26 joués:", int(data["is_wc26"].sum()))
