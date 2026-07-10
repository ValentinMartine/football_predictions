"""Normalise les noms d'équipes dans les données générées à partir de
data/team_name_map.json (nom source abrégé -> nom canonique).

Renomme tous les champs "team" des JSON de données ET les clés de club_logos.json,
pour que l'affichage du site et la recherche de logo restent alignés.
À exécuter comme dernière étape du pipeline, avant sync_to_site.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MAP = json.loads((DATA / "team_name_map.json").read_text(encoding="utf-8"))

TEAM_FIELD_FILES = [
    "standings.json", "bigfive_team_stats.json", "team_power.json",
    "understat_stats.json", "lineups.json", "bigfive_player_extra.json",
]


def walk(obj) -> int:
    """Remplace en place les valeurs des clés 'team' présentes dans MAP."""
    n = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "team" and isinstance(v, str) and v in MAP:
                obj[k] = MAP[v]
                n += 1
            else:
                n += walk(v)
    elif isinstance(obj, list):
        for x in obj:
            n += walk(x)
    return n


def main() -> int:
    total = 0
    for f in TEAM_FIELD_FILES:
        p = DATA / f
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        changed = walk(data)
        if changed:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {f} : {changed} nom(s) normalisé(s)")
            total += changed

    lp = DATA / "club_logos.json"
    if lp.exists():
        logos = json.loads(lp.read_text(encoding="utf-8"))
        renamed = {MAP.get(k, k): v for k, v in logos.items()}
        lp.write_text(json.dumps(dict(sorted(renamed.items())), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  club_logos.json : clés normalisées ({len(renamed)} logos)")

    print(f"normalize_names : {total} champ(s) 'team' normalisé(s) au total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
