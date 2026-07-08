"""
Récupère les événements de match factuels depuis FBref (via soccerdata) : substitutions
(entrant/sortant + minute), buts (buteur + passeur + minute) et cartons.

Produit data/match_events.json, indexé par la clé de match des prédictions
(YYYY-MM-DD|home|away), consommé par build_lineups.py pour remplacer l'appariement
inféré des remplaçants par des faits.

FBref limite le débit mais soccerdata met en cache : le premier passage sur ~200 matchs
est lent, les suivants sont quasi instantanés (seuls les nouveaux matchs sont récupérés).
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import soccerdata as sd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "match_events.json"
LEAGUES = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A", "GER-Bundesliga", "FRA-Ligue 1"]
MAX_MATCHES = 200

# Alias noms football-data.co.uk -> FBref (après normalisation).
ALIAS = {
    "espanol": "espanyol", "man city": "manchester city", "man united": "manchester united",
    "sociedad": "real sociedad", "ath bilbao": "athletic club", "ath madrid": "atletico madrid",
    "wolves": "wolverhampton wanderers", "nott'm forest": "nottingham forest",
    "sheffield united": "sheffield utd", "newcastle": "newcastle united",
    "leeds": "leeds united", "betis": "real betis",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = " ".join(s.lower().replace(".", " ").split())
    return ALIAS.get(s, s)


def parse_minute(raw) -> int | None:
    """'67’' -> 67 ; '90+1’' -> 90 ; None sinon."""
    if raw is None:
        return None
    m = re.match(r"\s*(\d+)", str(raw))
    return int(m.group(1)) if m else None


def _pick(cols, *cands):
    low = {str(c).lower(): c for c in cols}
    for cand in cands:
        if cand in low:
            return low[cand]
    for c in cols:
        for cand in cands:
            if cand in str(c).lower():
                return c
    return None


def main() -> int:
    preds = json.loads((ROOT / "data" / "predictions.json").read_text(encoding="utf-8"))
    recent = sorted(preds["recent_matches"], key=lambda m: m["date"], reverse=True)[:MAX_MATCHES]

    fb = sd.FBref(leagues=LEAGUES, seasons="2025")
    sched = fb.read_schedule().reset_index()
    sh = _pick(sched.columns, "home_team")
    sa = _pick(sched.columns, "away_team")
    sdt = _pick(sched.columns, "date")
    sgid = _pick(sched.columns, "game_id")
    sgame = _pick(sched.columns, "game")
    sched = sched.copy()
    sched["day"] = pd.to_datetime(sched[sdt]).dt.strftime("%Y-%m-%d")
    # (jour, home, away) -> (game_id pour le fetch, chaîne 'game' pour le filtrage)
    key_to_info = {(r["day"], norm(r[sh]), norm(r[sa])): (r[sgid], r[sgame]) for _, r in sched.iterrows()}

    # Associe chaque match récent à un match FBref.
    match_to_game: dict[str, str] = {}   # clé prédictions -> chaîne 'game' FBref
    gids = []                            # game_ids à récupérer
    for m in recent:
        info = key_to_info.get((m["date"], norm(m["home"]), norm(m["away"])))
        if info is None:
            for (day, nh, na), v in key_to_info.items():
                if day == m["date"] and (norm(m["home"]) in nh or nh in norm(m["home"])) \
                   and (norm(m["away"]) in na or na in norm(m["away"])):
                    info = v
                    break
        if info is not None:
            gid, game_str = info
            match_to_game[f"{m['date']}|{m['home']}|{m['away']}"] = game_str
            gids.append(gid)

    print(f"matchs associés à FBref : {len(gids)}/{len(recent)}")
    if not gids:
        OUT.write_text("{}", encoding="utf-8")
        return 0

    ev = fb.read_events(match_id=list(dict.fromkeys(gids))).reset_index()
    egame = _pick(ev.columns, "game")
    etype = _pick(ev.columns, "event_type")
    emin = _pick(ev.columns, "minute")
    ep1 = _pick(ev.columns, "player1")
    ep2 = _pick(ev.columns, "player2")

    def events_for(game_str) -> dict:
        rows = ev[ev[egame] == game_str]
        subs, goals, cards = [], [], []
        for _, r in rows.iterrows():
            t = str(r[etype])
            minute = parse_minute(r[emin])
            p1 = str(r[ep1]) if pd.notna(r[ep1]) else None
            p2 = str(r[ep2]) if pd.notna(r[ep2]) else None
            if t == "substitute_in":
                subs.append({"in": p1, "out": p2, "minute": minute})
            elif t == "goal":
                goals.append({"scorer": p1, "assist": p2, "minute": minute})
            elif t in ("yellow_card", "red_card"):
                cards.append({"player": p1, "type": t.replace("_card", ""), "minute": minute})
        return {"subs": subs, "goals": goals, "cards": cards}

    out = {k: events_for(game_str) for k, game_str in match_to_game.items()}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n_subs = sum(len(v["subs"]) for v in out.values())
    print(f"événements écrits : {len(out)} matchs, {n_subs} substitutions -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
