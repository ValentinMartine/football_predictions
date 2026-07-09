"""
Notes Sofascore PAR MATCH (Premier League 25/26) pour tester le rating glissant par journée.

Pour chaque match : par joueur, la note /10 (multi-critères, dépendante du poste) et le
maximum de données disponibles (minutes, dribbles réussis, passes précises, tirs cadrés,
tacles, passes clés, buts, passes déc.). ~4,8 s/match, ~30 min pour la saison.

Sortie : data/pl_player_match.json (liste de lignes joueur-match), sauvegardée au fil de l'eau.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import ScraperFC as sfc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "pl_player_match.json"
SEASON, LEAGUE = "25/26", "England Premier League"

RICH = {
    "rating": "rating", "minutesPlayed": "min", "goals": "g", "goalAssist": "a",
    "onTargetScoringAttempt": "sot", "accuratePass": "acc_pass", "totalPass": "tot_pass",
    "wonContest": "dribbles", "totalContest": "drib_att",
    "totalTackle": "tackles", "keyPass": "key_pass",
}


def _num(v):
    try:
        f = float(v)
        return f if pd.notna(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    ss = sfc.Sofascore()
    matches = ss.get_match_dicts(SEASON, LEAGUE)
    rows = []
    done = 0
    for m in matches:
        if str(m.get("status", {}).get("type", "")) not in ("finished", "Ended", "") and m.get("winnerCode") is None:
            continue
        mid = m.get("id")
        rnd = (m.get("roundInfo") or {}).get("round")
        home = (m.get("homeTeam") or {}).get("name")
        away = (m.get("awayTeam") or {}).get("name")
        winner = m.get("winnerCode")  # 1 dom, 2 ext, 3 nul
        if mid is None or home is None or away is None:
            continue
        try:
            url = ss.get_match_url_from_id(mid)
            df = ss.scrape_player_match_stats(url)
        except Exception:
            continue
        cols = {src: dst for src, dst in RICH.items() if src in df.columns}
        for _, r in df.iterrows():
            rec = {"round": rnd, "home": home, "away": away, "winner": winner,
                   "team": str(r.get("teamName", r.get("team", ""))),
                   "player": str(r.get("name", ""))}
            for src, dst in cols.items():
                rec[dst] = _num(r[src])
            rows.append(rec)
        done += 1
        if done % 20 == 0:
            OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            print(f"  {done} matchs scrapés...")
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"écrit {OUT.name} : {done} matchs, {len(rows)} lignes joueur-match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
