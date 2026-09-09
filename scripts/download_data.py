from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

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
            try:
                response = requests.get(url, timeout=30, headers={"User-Agent": "valentinmartine-football-predictions/1.0"})
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
                print(f"skip {season} {league}: {detail}")
                continue
            out.write_bytes(response.content)
            total += 1
            print(f"ok {season} {league} -> {out.relative_to(ROOT)}")
        if season == current_code:
            current_attempts = [record for record in records if record["season"] == current_code]
            if current_attempts and not any(record["ok"] for record in current_attempts):
                print(f"saison courante {current_code} indisponible ; arrêt rapide du téléchargement.")
                break
    current_records = [record for record in records if record["season"] == current_code]
    status = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "football-data.co.uk",
        "base_url": BASE_URL,
        "season_codes": all_seasons,
        "current_season": current_code,
        "files_ok": total,
        "files_checked": len(records),
        "current_season_files_ok": sum(1 for record in current_records if record["ok"]),
        "healthy": total > 0,
        "current_season_healthy": any(record["ok"] for record in current_records),
        "records": records,
    }
    SOURCE_STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"source status -> {SOURCE_STATUS.relative_to(ROOT)}")
    print(f"{total} fichiers telecharges")


if __name__ == "__main__":
    sys.exit(main())
