from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PUBLISHED_PREDICTIONS = ROOT / "data" / "predictions.json"
SOURCE_STATUS = ROOT / "data" / "source_status.json"


def run(command: list[str], check: bool = True, timeout: int | None = None) -> None:
    try:
        subprocess.run(command, cwd=ROOT, check=check, timeout=timeout)
    except subprocess.TimeoutExpired:
        if check:
            raise
        print(f"timeout non bloquant apres {timeout}s : {' '.join(command)}")


def main() -> None:
    # Étapes critiques : résultats + prédictions. Doivent réussir (échec = pipeline stoppé).
    run([sys.executable, "scripts/download_data.py"])
    if not any(RAW.glob("*.csv")) and PUBLISHED_PREDICTIONS.exists():
        print("Aucun CSV football-data disponible ; artefact publie conserve avec statut source.")
        if SOURCE_STATUS.exists():
            payload = json.loads(PUBLISHED_PREDICTIONS.read_text(encoding="utf-8"))
            payload["source_status"] = json.loads(SOURCE_STATUS.read_text(encoding="utf-8"))
            payload["refresh_status"] = "source_unavailable_existing_predictions_preserved"
            PUBLISHED_PREDICTIONS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    run([sys.executable, "-m", "src.export"])
    # Enrichissements dépendant de sources externes (Understat, Sofascore, API logos) :
    # non bloquants, pour que prédictions et « ma note » (calculée) se régénèrent même si
    # un scraping est temporairement bloqué (ex. IP de CI). L'enrichissement reprend au run suivant.
    run([sys.executable, "scripts/fetch_understat_stats.py"], check=False, timeout=180)
    run([sys.executable, "scripts/add_player_flags.py"], check=False, timeout=60)
    run([sys.executable, "scripts/fetch_sofascore_ratings.py"], check=False, timeout=180)
    run([sys.executable, "scripts/fetch_match_events.py"], check=False, timeout=240)
    run([sys.executable, "scripts/build_lineups.py"], check=False, timeout=90)
    run([sys.executable, "scripts/build_national_player_form.py"], check=False, timeout=180)
    run([sys.executable, "scripts/over_under_backtest.py"], check=False, timeout=90)
    run([sys.executable, "scripts/build_club_logos.py"], check=False, timeout=90)
    # Valeurs marchandes + salaires (Transfermarkt/Capology) : best-effort.
    run([sys.executable, "scripts/fetch_market_data.py"], check=False, timeout=180)
    # Compos + notes des autres championnats (Sofascore) : best-effort (scraping).
    run([sys.executable, "scripts/fetch_other_leagues_lineups.py"], check=False, timeout=180)
    # Normalisation des noms (données + clés de logos) : après tous les builders, avant sync.
    run([sys.executable, "scripts/normalize_names.py"], check=False, timeout=60)
    # Local convenience only: the website repository is not available in GitHub Actions.
    # Publication is handled by the valentinmartine repository workflows.
    run([sys.executable, "scripts/sync_to_site.py"], check=False, timeout=30)


if __name__ == "__main__":
    main()
