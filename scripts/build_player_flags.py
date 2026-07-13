"""Construit le référentiel de nationalités affiché dans les tableaux joueurs.

Les pages FBref déjà mises en cache par soccerdata sont relues localement : aucune
requête web n'est émise. La clé est le nom normalisé, ce qui permet de réutiliser la
nationalité d'un joueur dans les saisons historiques où la source ne la répète pas.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from add_player_flags import FIFA2ISO, SUBDIVISION_FLAGS, _iso_to_emoji, _nation_code, _norm

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("C:/Users/valen/soccerdata/data/FBref")
OUT = ROOT / "data" / "player_flags.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/player_flags.json")


def flag_for(nation: object) -> str | None:
    code = _nation_code(nation)
    if not code:
        return None
    if code in SUBDIVISION_FLAGS:
        return SUBDIVISION_FLAGS[code]
    iso = FIFA2ISO.get(code)
    return _iso_to_emoji(iso) if iso else None


def main() -> int:
    flags: dict[str, str] = {}
    for path in sorted(CACHE.glob("players_*_standard.html")):
        for table in pd.read_html(path):
            columns = [c[-1] if isinstance(c, tuple) else c for c in table.columns]
            if "Player" not in columns or "Nation" not in columns:
                continue
            table.columns = columns
            for _, row in table.iterrows():
                player = str(row.get("Player", ""))
                flag = flag_for(row.get("Nation"))
                if player and player != "Player" and flag:
                    flags[_norm(player)] = flag
            break

    OUT.write_text(json.dumps(flags, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(flags, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(flags)} nationalités extraites depuis {len(list(CACHE.glob('players_*_standard.html')))} caches FBref")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
