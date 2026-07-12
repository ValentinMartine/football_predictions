"""
Notes Sofascore PAR MATCH pour plusieurs ligues-saisons (pour répliquer le test du rating
glissant par joueur sur les 5 grands championnats). ~4,8 s/match.

Écrit un fichier par ligue-saison : data/player_match/<slug>.json, sauvegardé au fil de l'eau.
Reprend là où il s'est arrêté (les matchs déjà scrapés sont sautés).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import ScraperFC as sfc

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "data" / "player_match"
OUTDIR.mkdir(parents=True, exist_ok=True)
SEASON = "25/26"
LEAGUES = {
    "Spain La Liga": "esp_2526",
    "Italy Serie A": "ita_2526",
    "Germany Bundesliga": "ger_2526",
    "France Ligue 1": "fra_2526",
}
RICH = {"rating": "rating", "minutesPlayed": "min", "goals": "g", "goalAssist": "a",
        "onTargetScoringAttempt": "sot", "accuratePass": "acc_pass", "totalPass": "tot_pass",
        "wonContest": "dribbles", "totalContest": "drib_att", "totalTackle": "tackles",
        "keyPass": "key_pass",
        # Stats défensives / gardien (note v2) : accumulées pour les prochaines saisons.
        "saves": "sv", "goalsPrevented": "gp", "penaltySave": "ps",
        "wonTackle": "tw", "interceptionWon": "itc", "totalClearance": "clr",
        "blockedScoringAttempt": "blk", "outfielderBlock": "oblk",
        "duelWon": "dw", "duelLost": "dl", "aerialWon": "aw",
        "errorLeadToAShot": "els", "bigChanceCreated": "bcc", "bigChanceMissed": "bcm"}


def _num(v):
    try:
        f = float(v)
        return f if pd.notna(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    ss = sfc.Sofascore()
    for league, slug in LEAGUES.items():
        out = OUTDIR / f"{slug}.json"
        rows = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
        seen = {(r["round"], r["home"], r["away"]) for r in rows}
        try:
            matches = ss.get_match_dicts(SEASON, league)
        except Exception as exc:  # noqa: BLE001
            print(f"{league}: get_match_dicts {type(exc).__name__}")
            continue
        done = 0
        for m in matches:
            mid = m.get("id")
            rnd = (m.get("roundInfo") or {}).get("round")
            home = (m.get("homeTeam") or {}).get("name")
            away = (m.get("awayTeam") or {}).get("name")
            winner = m.get("winnerCode")
            if mid is None or home is None or away is None or winner not in (1, 2, 3):
                continue
            if (rnd, home, away) in seen:
                continue
            try:
                df = ss.scrape_player_match_stats(ss.get_match_url_from_id(mid))
            except Exception:
                continue
            cols = {s: d for s, d in RICH.items() if s in df.columns}
            for _, r in df.iterrows():
                rec = {"round": rnd, "home": home, "away": away, "winner": winner,
                       "team": str(r.get("teamName", "")), "player": str(r.get("name", ""))}
                for s, d in cols.items():
                    rec[d] = _num(r[s])
                rows.append(rec)
            done += 1
            if done % 20 == 0:
                out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                print(f"  {slug}: {done} nouveaux matchs...")
        out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"{slug}: {done} matchs scrapés (total {len(rows)} lignes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
