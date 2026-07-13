"""Recompute other_leagues_ratings.json from already exported Sofascore lineups.

This is the cheap, deterministic path used by the website: it aggregates the player
ratings already present in data/other_leagues_lineups.json, without re-scraping.
Use backfill_other_leagues_ratings.py only when we want a deeper historical store.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINEUPS = ROOT / "data" / "other_leagues_lineups.json"

spec = importlib.util.spec_from_file_location(
    "other_lineups", ROOT / "scripts" / "fetch_other_leagues_lineups.py"
)
other_lineups = importlib.util.module_from_spec(spec)
spec.loader.exec_module(other_lineups)


def season_label(value: object) -> str | None:
    text = str(value or "").strip()
    match = re.match(r"^(\d{2})/(\d{2})$", text)
    if match:
        return f"20{match.group(1)}-20{match.group(2)}"
    return text or None


def parse_score(score: object) -> tuple[int | None, int | None]:
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", str(score or ""))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def main() -> int:
    if not LINEUPS.exists():
        raise FileNotFoundError(LINEUPS)
    payload = json.loads(LINEUPS.read_text(encoding="utf-8"))
    store = {
        "source": "Sofascore lineups aggregate",
        "players": {},
        "teams": {},
        "seen": {},
    }
    match_count = 0
    for code, league in (payload.get("leagues") or {}).items():
        name = league.get("name") or code
        flag = league.get("flag") or ""
        season = season_label(league.get("season"))
        for match in league.get("matches") or []:
            home = match.get("home")
            away = match.get("away")
            hs, away_score = parse_score(match.get("score"))
            if not home or not away or hs is None or away_score is None:
                continue
            match_id = match.get("id") or f"{code}|{match.get('date')}|{home}|{away}"
            other_lineups.update_ratings(
                store,
                code,
                name,
                flag,
                season_label(match.get("season")) or season,
                match_id,
                home,
                away,
                hs,
                away_score,
                match.get("home_lineup") or [],
                match.get("away_lineup") or [],
            )
            match_count += 1
    other_lineups.save_ratings(store)
    print(
        f"other_leagues_ratings.json: {len(store['teams'])} teams, "
        f"{len(store['players'])} players, {match_count} matches"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())