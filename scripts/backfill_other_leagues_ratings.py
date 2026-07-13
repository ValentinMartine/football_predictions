"""Backfill SAISON du magasin de notes des autres championnats (other_leagues_ratings.json).

Scrape tous les matchs terminés de la saison courante de chaque ligue (dédupliqué par id,
reprenable), pour que « note calculée » et « Puissance XI calculée » reposent sur la saison
entière et non sur les 8 derniers matchs affichés. Long (~4 000 matchs) : lancer par ligue
en tâche de fond ; le magasin s'améliore au fil de l'eau.

Usage : python scripts/backfill_other_leagues_ratings.py [CODE]
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("foll", ROOT / "scripts" / "fetch_other_leagues_lineups.py")
foll = importlib.util.module_from_spec(spec)
spec.loader.exec_module(foll)


def main() -> int:
    import ScraperFC as sfc
    sofa = sfc.Sofascore()
    DIV = foll._div_meta()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    targets = {only: foll.LEAGUE_MAP[only]} if only in foll.LEAGUE_MAP else foll.LEAGUE_MAP
    store = foll.load_ratings()

    for code, league in targets.items():
        name, flag = DIV.get(code, (league, "🏳️"))
        try:
            seasons = sofa.get_valid_seasons(league)
            matches = []
            season = None
            for yr in list(seasons.keys() if isinstance(seasons, dict) else seasons):
                ms = sofa.get_match_dicts(yr, league)
                done = [m for m in ms if m.get("status", {}).get("type") == "finished"]
                if done:
                    season = yr
                    matches = done
                    break
            seen = set(store["seen"].get(code, []))
            todo = [m for m in matches if m.get("id") not in seen]
            print(f"{code} {league}: {len(todo)} match(s) à intégrer ({len(seen)} déjà faits)", flush=True)
            done_n = 0
            for m in todo:
                ht = m.get("homeTeam", {}).get("name")
                at = m.get("awayTeam", {}).get("name")
                hs = m.get("homeScore", {}).get("current")
                as_ = m.get("awayScore", {}).get("current")
                try:
                    ps = sofa.scrape_player_match_stats(m["id"])
                except Exception:  # noqa: BLE001
                    continue
                home, away = foll._players_from_stats(ps, ht, at)
                if not home and not away:
                    continue
                foll.update_ratings(store, code, name, flag, season, m.get("id"), ht, at, hs, as_, home, away)
                done_n += 1
                if done_n % 15 == 0:
                    foll.save_ratings(store)
                    print(f"  {code}: {done_n}/{len(todo)}", flush=True)
            foll.save_ratings(store)
            print(f"  {code}: terminé (+{done_n})", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  {code}: échec ({exc})", flush=True)
            foll.save_ratings(store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
