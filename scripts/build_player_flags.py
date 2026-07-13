"""Construit le référentiel de nationalités affiché dans les tableaux joueurs.

Les pages FBref déjà mises en cache par soccerdata sont relues localement : aucune
requête web n'est émise. La clé est le nom normalisé, ce qui permet de réutiliser la
nationalité d'un joueur dans les saisons historiques où la source ne la répète pas.
"""
from __future__ import annotations

import json
import csv
from pathlib import Path

import pandas as pd
import requests
from babel import Locale

from add_player_flags import FIFA2ISO, SUBDIVISION_FLAGS, _iso_to_emoji, _nation_code, _norm

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("C:/Users/valen/soccerdata/data/FBref")
OUT = ROOT / "data" / "player_flags.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/player_flags.json")
NATIONAL_FORM = ROOT / "data" / "national_player_form.json"
HISTORY = ROOT / "data" / "computed_ratings_history.json"
TEAM_POWER = ROOT / "data" / "team_power.json"
REEP_CACHE = ROOT / "data" / "cache" / "reep_people.csv"
REEP_URL = "https://raw.githubusercontent.com/withqwerty/reep/main/data/people.csv"
REEP_NAMES_CACHE = ROOT / "data" / "cache" / "reep_names.csv"
REEP_NAMES_URL = "https://raw.githubusercontent.com/withqwerty/reep/main/data/names.csv"

COUNTRY_ALIASES = {
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "kosovo": "XK", "ivory coast": "CI", "cape verde": "CV", "south korea": "KR",
    "north korea": "KP", "iran": "IR", "russia": "RU", "moldova": "MD",
    "bolivia": "BO", "venezuela": "VE", "tanzania": "TZ", "syria": "SY",
}


def flag_for(nation: object) -> str | None:
    code = _nation_code(nation)
    if not code:
        return None
    if code in SUBDIVISION_FLAGS:
        return SUBDIVISION_FLAGS[code]
    iso = FIFA2ISO.get(code)
    return _iso_to_emoji(iso) if iso else None


def country_flag(country: object) -> str | None:
    """Convertit le pays en emoji à partir du registre Reep/Wikidata."""
    if not isinstance(country, str) or not country.strip():
        return None
    name = country.strip().lower()
    code = COUNTRY_ALIASES.get(name)
    if not code:
        territories = Locale("en").territories
        code = next((key for key, value in territories.items() if str(value).lower() == name), None)
    return _iso_to_emoji(code) if code and len(code) == 2 else None


def download_if_missing(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    tmp = path.with_suffix(".tmp")
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    tmp.replace(path)


def reep_flags() -> dict[str, str]:
    """Charge les nationalités Reep et exclut les homonymes contradictoires."""
    download_if_missing(REEP_URL, REEP_CACHE)
    download_if_missing(REEP_NAMES_URL, REEP_NAMES_CACHE)

    candidates: dict[str, set[str]] = {}
    by_id: dict[str, str] = {}
    with REEP_CACHE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("type") != "player":
                continue
            flag = country_flag(row.get("nationality"))
            name = _norm(row.get("name", ""))
            if flag and name:
                candidates.setdefault(name, set()).add(flag)
                by_id[row["reep_id"]] = flag

    # Les alias sont fournis par le même registre, avec l'identifiant canonique :
    # ils corrigent les accents, initiales et translittérations sans fuzzy matching.
    with REEP_NAMES_CACHE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            flag = by_id.get(row.get("reep_id", ""))
            alias = _norm(row.get("alias", ""))
            if flag and alias:
                candidates.setdefault(alias, set()).add(flag)
    return {name: next(iter(values)) for name, values in candidates.items() if len(values) == 1}


def required_names() -> set[str]:
    """N'exporte au site que les joueurs réellement affichables dans Big Five."""
    names: set[str] = set()
    if HISTORY.exists():
        history = json.loads(HISTORY.read_text(encoding="utf-8"))
        names.update(_norm(row.get("player", "")) for row in history.get("players", {}).values())
    if TEAM_POWER.exists():
        power = json.loads(TEAM_POWER.read_text(encoding="utf-8"))
        for team in power.get("teams", []):
            names.update(_norm(row.get("player", "")) for row in team.get("players", []))
    return {name for name in names if name}


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

    # La base de forme nationale est construite à partir des nationalités FBref ;
    # elle complète les joueurs qui ne figurent pas dans les quatre caches détaillés.
    if NATIONAL_FORM.exists():
        national_form = json.loads(NATIONAL_FORM.read_text(encoding="utf-8"))
        for country in national_form.get("countries", []):
            flag = country.get("flag")
            if not flag:
                continue
            for player in country.get("top_players", []):
                name = player.get("player")
                if name:
                    flags.setdefault(_norm(name), flag)

    for name, flag in reep_flags().items():
        flags.setdefault(name, flag)

    needed = required_names()
    flags = {name: flag for name, flag in flags.items() if name in needed}
    OUT.write_text(json.dumps(flags, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(flags, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(flags)}/{len(needed)} nationalités exportées depuis {len(list(CACHE.glob('players_*_standard.html')))} caches FBref et Reep")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
