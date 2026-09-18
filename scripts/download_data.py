from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SOURCE_STATUS = ROOT / "data" / "source_status.json"
RAW.mkdir(parents=True, exist_ok=True)

LEAGUES = {
    "E0": "Premier League", "SP1": "La Liga", "I1": "Serie A", "D1": "Bundesliga", "F1": "Ligue 1",
    "E1": "Championship", "E2": "League One", "E3": "League Two",
    "SC0": "Scottish Premiership", "SC1": "Scottish Championship",
    "D2": "2. Bundesliga", "I2": "Serie B", "SP2": "La Liga 2", "F2": "Ligue 2",
    "N1": "Eredivisie", "B1": "Jupiler Pro League", "P1": "Primeira Liga",
    "T1": "Super Lig", "G1": "Super League Greece",
}
BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
FOOTBALL_DATA_ORG_URL = "https://api.football-data.org/v4/competitions/{competition}/matches"
REQUEST_TIMEOUT = (5, 20)
HEADERS = {"User-Agent": "valentinmartine-football-predictions/1.0"}
FOOTBALL_DATA_ORG_COMPETITIONS = {
    "E0": "PL",
    "SP1": "PD",
    "I1": "SA",
    "D1": "BL1",
    "F1": "FL1",
}
FOOTBALL_DATA_COLUMNS = [
    "Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
    "HTHG", "HTAG", "HTR", "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC",
    "HY", "AY", "HR", "AR", "B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA",
    "MaxH", "MaxD", "MaxA", "B365CH", "B365CD", "B365CA", "AvgCH", "AvgCD",
    "AvgCA", "MaxCH", "MaxCD", "MaxCA",
]
TEAM_ALIASES = {
    "FC Internazionale Milano": "Inter",
    "FC Bayern München": "Bayern Munich",
    "Bayer 04 Leverkusen": "Leverkusen",
    "Borussia Dortmund": "Dortmund",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "Borussia Mönchengladbach": "M'gladbach",
    "Paris Saint-Germain FC": "Paris SG",
    "Olympique Lyonnais": "Lyon",
    "Olympique de Marseille": "Marseille",
    "OGC Nice": "Nice",
    "AS Monaco FC": "Monaco",
    "Stade Rennais FC 1901": "Rennes",
    "Real Madrid CF": "Real Madrid",
    "FC Barcelona": "Barcelona",
    "Club Atlético de Madrid": "Ath Madrid",
    "Real Sociedad de Fútbol": "Sociedad",
    "Villarreal CF": "Villarreal",
    "Sevilla FC": "Sevilla",
    "Athletic Club": "Ath Bilbao",
    "Manchester United FC": "Man United",
    "Manchester City FC": "Man City",
    "Tottenham Hotspur FC": "Tottenham",
    "Newcastle United FC": "Newcastle",
    "West Ham United FC": "West Ham",
    "Brighton & Hove Albion FC": "Brighton",
    "Wolverhampton Wanderers FC": "Wolves",
    "Nottingham Forest FC": "Nott'm Forest",
    "AFC Bournemouth": "Bournemouth",
}


def log(message: str) -> None:
    """Print immediately so GitHub Actions exposes long-running source checks."""
    print(message, flush=True)


def is_usable_cached_raw(path: Path) -> bool:
    """Return True when a historical CSV can be reused instead of downloaded again."""
    return path.exists() and path.stat().st_size > 0


def current_season_start_year(today: date | None = None) -> int:
    """Return the start year of the active European football season."""
    current = today or date.today()
    return current.year if current.month >= 7 else current.year - 1


def season_code(start_year: int) -> str:
    """Convert a start year to football-data.co.uk's two-year code."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def seasons_to_fetch(first_start_year: int = 2015, today: date | None = None) -> list[str]:
    """Fetch historical seasons through the active one, e.g. 2026/27 -> 2627."""
    last_start_year = current_season_start_year(today)
    return [season_code(year) for year in range(first_start_year, last_start_year + 1)]


def canonical_team_name(team: dict[str, Any]) -> str:
    """Return the closest football-data.co.uk style team name for fallback rows."""
    for field in ("shortName", "name", "tla"):
        value = str(team.get(field) or "").strip()
        if value:
            return TEAM_ALIASES.get(value, value.removesuffix(" FC").removesuffix(" CF").strip())
    return ""


def result_code(home_goals: int, away_goals: int) -> str:
    """Convert full-time goals to football-data.co.uk's H/D/A result code."""
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def football_data_org_rows(payload: dict[str, Any], league: str) -> list[dict[str, Any]]:
    """Convert football-data.org matches to a minimal football-data.co.uk CSV schema."""
    rows: list[dict[str, Any]] = []
    for match in payload.get("matches", []):
        if match.get("status") != "FINISHED":
            continue
        full_time = (match.get("score") or {}).get("fullTime") or {}
        home_goals = full_time.get("home")
        away_goals = full_time.get("away")
        if home_goals is None or away_goals is None:
            continue
        day = datetime.fromisoformat(str(match["utcDate"]).replace("Z", "+00:00"))
        row = {column: None for column in FOOTBALL_DATA_COLUMNS}
        row.update({
            "Div": league,
            "Date": day.strftime("%d/%m/%Y"),
            "Time": day.strftime("%H:%M"),
            "HomeTeam": canonical_team_name(match.get("homeTeam") or {}),
            "AwayTeam": canonical_team_name(match.get("awayTeam") or {}),
            "FTHG": int(home_goals),
            "FTAG": int(away_goals),
            "FTR": result_code(int(home_goals), int(away_goals)),
        })
        if row["HomeTeam"] and row["AwayTeam"]:
            rows.append(row)
    return rows


def fetch_football_data_org_current_season(current_code: str, records: list[dict]) -> int:
    """Fetch finished Big Five current-season matches via football-data.org when configured."""
    token = os.environ.get("FOOTBALL_DATA_API_TOKEN")
    if not token:
        records.append({
            "season": current_code,
            "source": "football-data.org",
            "ok": False,
            "error": "FOOTBALL_DATA_API_TOKEN missing",
        })
        return 0

    total = 0
    season_start = 2000 + int(current_code[:2])
    headers = {
        "X-Auth-Token": token,
        "User-Agent": "valentinmartine-football-predictions/1.0",
    }
    for league, competition in FOOTBALL_DATA_ORG_COMPETITIONS.items():
        url = FOOTBALL_DATA_ORG_URL.format(competition=competition)
        params = {"season": season_start, "status": "FINISHED"}
        out = RAW / f"{current_code}_{league}.csv"
        record = {
            "season": current_code,
            "league": league,
            "competition": competition,
            "source": "football-data.org",
            "url": url,
            "ok": False,
            "rows": 0,
            "error": None,
        }
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=headers)
            record["status_code"] = response.status_code
            response.raise_for_status()
            rows = football_data_org_rows(response.json(), league)
            record["rows"] = len(rows)
            if rows:
                import pandas as pd

                pd.DataFrame(rows, columns=FOOTBALL_DATA_COLUMNS).to_csv(out, index=False)
                total += 1
                record["ok"] = True
                log(f"ok {current_code} {league} -> {out.relative_to(ROOT)} via football-data.org")
            else:
                record["error"] = "no finished matches returned"
                log(f"skip {current_code} {league}: no finished matches via football-data.org")
        except Exception as exc:  # noqa: BLE001
            record["error"] = str(exc)
            log(f"skip {current_code} {league}: football-data.org {exc}")
        records.append(record)
    return total


def main() -> None:
    total = 0
    records = []
    all_seasons = seasons_to_fetch()
    current_code = season_code(current_season_start_year())
    seasons = [current_code] + [season for season in all_seasons if season != current_code]
    for season in seasons:
        for league in LEAGUES:
            url = BASE_URL.format(season=season, league=league)
            out = RAW / f"{season}_{league}.csv"
            if season != current_code and is_usable_cached_raw(out):
                records.append({
                    "season": season,
                    "league": league,
                    "url": url,
                    "ok": True,
                    "source": "cache",
                    "cached": True,
                    "status_code": None,
                    "error": None,
                })
                total += 1
                log(f"cache {season} {league} -> {out.relative_to(ROOT)}")
                continue
            try:
                response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
                ok = response.ok and "Div,Date" in response.text[:500]
                status_code = response.status_code
                error = None
            except requests.RequestException as exc:
                response = None
                ok = False
                status_code = None
                error = str(exc)
            records.append({
                "season": season,
                "league": league,
                "url": url,
                "ok": ok,
                "status_code": status_code,
                "error": error,
            })
            if not ok or response is None:
                detail = f"HTTP {status_code}" if status_code is not None else error
                log(f"skip {season} {league}: {detail}")
                continue
            out.write_bytes(response.content)
            total += 1
            log(f"ok {season} {league} -> {out.relative_to(ROOT)}")
        if season == current_code:
            current_attempts = [record for record in records if record["season"] == current_code]
            if current_attempts and not any(record["ok"] for record in current_attempts):
                print(f"saison courante {current_code} indisponible ; arrêt rapide du téléchargement.")
                total += fetch_football_data_org_current_season(current_code, records)
                break
    current_records = [record for record in records if record["season"] == current_code]
    status = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "football-data.co.uk",
        "fallback_source": "football-data.org",
        "base_url": BASE_URL,
        "season_codes": all_seasons,
        "current_season": current_code,
        "files_ok": total,
        "files_checked": len(records),
        "current_season_files_ok": sum(1 for record in current_records if record["ok"]),
        "healthy": total > 0,
        "current_season_healthy": any(record["ok"] for record in current_records),
        "current_season_has_bookmaker_odds": any(
            record["ok"] and record.get("source", "football-data.co.uk") == "football-data.co.uk"
            for record in current_records
        ),
        "records": records,
    }
    SOURCE_STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"source status -> {SOURCE_STATUS.relative_to(ROOT)}")
    log(f"{total} fichiers telecharges")


if __name__ == "__main__":
    sys.exit(main())
