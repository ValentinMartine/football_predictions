"""Download international match results and penalty shootout metadata."""
from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BASE_URL = "https://raw.githubusercontent.com/martj42/international_results/master"


def main() -> None:
    DATA.mkdir(exist_ok=True)
    for name in ("results.csv", "shootouts.csv"):
        urlretrieve(f"{BASE_URL}/{name}", DATA / name)
        print(f"Downloaded data/{name}")


if __name__ == "__main__":
    main()
