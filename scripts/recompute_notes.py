"""Recalcule « ma note » v2 dans worldcup_lineups.json et other_leagues_lineups.json à
partir des stats brutes stockées par joueur (sv, gp, tw, itc, ..., mins, cards).

Permet de recalibrer la formule sans re-scraper Sofascore. Copie aussi vers le site.
La formule DOIT rester identique à compute_note de fetch_wc_lineups.py /
fetch_other_leagues_lineups.py (source de vérité : ce fichier après recalibrage).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data")
POS_GROUP = {"GK": "GK", "DC": "DEF", "DR": "DEF", "DL": "DEF", "MC": "MID", "FW": "ATT"}

TARGETS = [
    (ROOT / "world_cup" / "data" / "worldcup_lineups.json", SITE / "worldcup_lineups.json", "wc"),
    (ROOT / "data" / "other_leagues_lineups.json", SITE / "other_leagues_lineups.json", "other"),
]


def compute_note(group: str, p: dict, conceded: int) -> float:
    mins = p.get("mins", 90) or 90
    w = min(1.0, max(0.2, mins / 90.0))
    off = (1.3 * p.get("g", 0) + 0.8 * p.get("a", 0) + 0.4 * p.get("xg", 0.0) + 0.4 * p.get("xa", 0.0)
           + 0.3 * p.get("bcc", 0) + 0.12 * p.get("kp", 0) - 0.3 * p.get("bcm", 0))
    dact = min(1.5, 0.09 * (p.get("tw", 0) + p.get("itc", 0))
               + 0.05 * (p.get("clr", 0) + p.get("blk", 0) + p.get("oblk", 0))
               + 0.04 * (p.get("dw", 0) - p.get("dl", 0)) + 0.04 * p.get("aw", 0))
    cards = p.get("cards") or []
    discipline = sum(-1.0 if c.get("type") in ("red", "yellowRed") else -0.3 for c in cards)
    errors = -0.7 * p.get("els", 0)

    def csb(strong: float, weak: float) -> float:
        if conceded <= 0:
            return strong
        if conceded == 1:
            return weak
        if conceded == 2:
            return 0.0
        return -0.4 * (conceded - 2)

    if group == "GK":
        gp = max(-2.0, min(2.0, p.get("gp", 0.0)))
        note = (6.4 + w * (0.65 * gp + 0.10 * p.get("sv", 0) + 0.8 * p.get("ps", 0))
                + w * csb(0.6, 0.25) + 0.4 * off + discipline + errors)
    elif group == "DEF":
        note = 6.0 + off + w * dact + w * csb(0.8, 0.3) + discipline + errors
    elif group == "MID":
        note = 6.0 + off + w * 0.6 * dact + w * csb(0.25, 0.1) + discipline + errors
    else:
        note = 6.0 + off + w * 0.3 * dact + discipline + errors
    return round(min(10.0, max(3.0, note)), 1)


def _recompute_match(home: list, away: list) -> int:
    hg = sum(int(p.get("g", 0)) for p in home)
    ag = sum(int(p.get("g", 0)) for p in away)
    changed = 0
    for players, conceded in ((home, ag), (away, hg)):
        for p in players:
            new = compute_note(POS_GROUP.get(p.get("pos", ""), "ATT"), p, conceded)
            if p.get("note") != new:
                p["note"] = new
                changed += 1
    return changed


def main() -> int:
    for src, dst, kind in TARGETS:
        if not src.exists():
            print(f"absent : {src.name}")
            continue
        data = json.loads(src.read_text(encoding="utf-8"))
        changed = 0
        if kind == "wc":
            for m in data.values():
                if isinstance(m, dict) and "home" in m:
                    changed += _recompute_match(m.get("home") or [], m.get("away") or [])
        else:
            for league in (data.get("leagues") or {}).values():
                for m in league.get("matches", []):
                    changed += _recompute_match(m.get("home_lineup") or [], m.get("away_lineup") or [])
        blob = json.dumps(data, ensure_ascii=False, indent=1)
        src.write_text(blob, encoding="utf-8")
        if dst.parent.exists():
            dst.write_text(blob, encoding="utf-8")
        print(f"{src.name} : {changed} note(s) recalculée(s) + copie site")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
