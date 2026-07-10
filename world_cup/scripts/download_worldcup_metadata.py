"""Download World Cup metadata used for candidate feature groups."""
from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BASE_URL = "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv"


def main() -> None:
    DATA.mkdir(exist_ok=True)
    for source, target in {
        "teams.csv": "worldcup_teams.csv",
        "matches.csv": "worldcup_matches.csv",
    }.items():
        urlretrieve(f"{BASE_URL}/{source}", DATA / target)
        print(f"Downloaded data/{target}")


if __name__ == "__main__":
    main()
