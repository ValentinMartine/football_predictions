"""Copie les données générées du projet clubs vers le dossier public du site
(valentinmartine/public/data), pour publication (Vercel déploie au push)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data")

# (source dans data/, nom de destination sur le site)
FILES = [
    ("predictions.json", "football_clubs_predictions.json"),
    ("lineups.json", "lineups.json"),
    ("understat_stats.json", "understat_stats.json"),
    ("national_player_form.json", "national_player_form.json"),
    ("team_power.json", "team_power.json"),
    ("over_under_report.json", "over_under_report.json"),
]


def main() -> int:
    if not SITE.exists():
        print(f"Dossier site introuvable : {SITE}", file=sys.stderr)
        return 1
    copied = 0
    for src_name, dst_name in FILES:
        src = ROOT / "data" / src_name
        if not src.exists():
            print(f"  (ignoré, absent) {src_name}")
            continue
        shutil.copy2(src, SITE / dst_name)
        copied += 1
        print(f"  copié {src_name} -> {dst_name}")
    print(f"sync_to_site : {copied} fichier(s) copié(s) vers {SITE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
