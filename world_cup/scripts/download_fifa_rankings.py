from __future__ import annotations

from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fifa_rankings.csv"
URL = "https://raw.githubusercontent.com/Dato-Futbol/fifa-ranking/refs/heads/master/ranking_fifa_historical.csv"


def main() -> None:
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    OUT.write_bytes(response.content)
    print(f"Ecrit {OUT}")


if __name__ == "__main__":
    main()
