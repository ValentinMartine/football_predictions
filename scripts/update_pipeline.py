from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], check: bool = True) -> None:
    subprocess.run(command, cwd=ROOT, check=check)


def main() -> None:
    run([sys.executable, "scripts/download_data.py"])
    run([sys.executable, "-m", "src.export"])
    run([sys.executable, "scripts/fetch_understat_stats.py"])
    run([sys.executable, "scripts/add_player_flags.py"])
    run([sys.executable, "scripts/fetch_sofascore_ratings.py"])
    run([sys.executable, "scripts/fetch_match_events.py"])
    run([sys.executable, "scripts/build_lineups.py"])
    run([sys.executable, "scripts/build_national_player_form.py"])
    run([sys.executable, "scripts/over_under_backtest.py"])
    # Logos : best-effort (dépend d'une API externe) pour ne pas bloquer le pipeline.
    run([sys.executable, "scripts/build_club_logos.py"], check=False)
    # Normalisation des noms (données + clés de logos) : après tous les builders, avant sync.
    run([sys.executable, "scripts/normalize_names.py"])
    run([sys.executable, "scripts/sync_to_site.py"])


if __name__ == "__main__":
    main()
