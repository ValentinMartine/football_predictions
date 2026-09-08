from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PUBLISHED_PREDICTIONS = ROOT / "data" / "predictions.json"


def run(command: list[str], check: bool = True) -> None:
    subprocess.run(command, cwd=ROOT, check=check)


def main() -> None:
    # Étapes critiques : résultats + prédictions. Doivent réussir (échec = pipeline stoppé).
    run([sys.executable, "scripts/download_data.py"])
    if not any(RAW.glob("*.csv")) and PUBLISHED_PREDICTIONS.exists():
        print("Aucun CSV football-data disponible ; artefact publie conserve.")
        return
    run([sys.executable, "-m", "src.export"])
    # Enrichissements dépendant de sources externes (Understat, Sofascore, API logos) :
    # non bloquants, pour que prédictions et « ma note » (calculée) se régénèrent même si
    # un scraping est temporairement bloqué (ex. IP de CI). L'enrichissement reprend au run suivant.
    run([sys.executable, "scripts/fetch_understat_stats.py"], check=False)
    run([sys.executable, "scripts/add_player_flags.py"], check=False)
    run([sys.executable, "scripts/fetch_sofascore_ratings.py"], check=False)
    run([sys.executable, "scripts/fetch_match_events.py"], check=False)
    run([sys.executable, "scripts/build_lineups.py"], check=False)
    run([sys.executable, "scripts/build_national_player_form.py"], check=False)
    run([sys.executable, "scripts/over_under_backtest.py"], check=False)
    run([sys.executable, "scripts/build_club_logos.py"], check=False)
    # Valeurs marchandes + salaires (Transfermarkt/Capology) : best-effort.
    run([sys.executable, "scripts/fetch_market_data.py"], check=False)
    # Compos + notes des autres championnats (Sofascore) : best-effort (scraping).
    run([sys.executable, "scripts/fetch_other_leagues_lineups.py"], check=False)
    # Normalisation des noms (données + clés de logos) : après tous les builders, avant sync.
    run([sys.executable, "scripts/normalize_names.py"], check=False)
    run([sys.executable, "scripts/sync_to_site.py"])


if __name__ == "__main__":
    main()
