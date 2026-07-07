from __future__ import annotations

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

LEAGUES = {
    "E0": "Premier League",
    "SP1": "La Liga",
    "I1": "Serie A",
    "D1": "Bundesliga",
    "F1": "Ligue 1",
}
SEASONS = [f"{y:02d}{y + 1:02d}" for y in range(15, 26)]
BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def main() -> None:
    total = 0
    for season in SEASONS:
        for league in LEAGUES:
            url = BASE_URL.format(season=season, league=league)
            out = RAW / f"{season}_{league}.csv"
            response = requests.get(url, timeout=30)
            if not response.ok or "Div,Date" not in response.text[:500]:
                print(f"skip {season} {league}: HTTP {response.status_code}")
                continue
            out.write_bytes(response.content)
            total += 1
            print(f"ok {season} {league} -> {out.relative_to(ROOT)}")
    print(f"{total} fichiers telecharges")


if __name__ == "__main__":
    sys.exit(main())
