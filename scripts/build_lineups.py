"""
Build recent match lineups from Understat player-match data.

Understat gives player minutes and substitute status, but not the exact
replacement pairs. We infer pairs by team from substitution minutes and the
outgoing player's position, then keep the inferred confidence in the JSON.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import soccerdata as sd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "lineups.json"
LEAGUES = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A", "GER-Bundesliga", "FRA-Ligue 1"]

# Display order: goalkeeper, defenders, midfielders, attackers, bench.
POS_ORDER = {
    "GK": 0, "DC": 1, "DR": 2, "DL": 3, "DMC": 4, "DMR": 5, "DML": 6,
    "MC": 7, "MR": 8, "ML": 9, "AMC": 10, "AMR": 11, "AML": 12,
    "FW": 13, "FWR": 14, "FWL": 15, "Sub": 99,
}

POS_GROUP = {
    "GK": "GK",
    "DC": "DEF", "DR": "DEF", "DL": "DEF",
    "DMC": "MID", "DMR": "MID", "DML": "MID", "MC": "MID", "MR": "MID", "ML": "MID",
    "AMC": "ATT", "AMR": "ATT", "AML": "ATT", "FW": "ATT", "FWR": "ATT", "FWL": "ATT",
    "Sub": "SUB",
}


# football-data.co.uk aliases -> Understat names after normalization.
ALIAS = {
    "espanol": "espanyol", "man city": "manchester city", "man united": "manchester united",
    "sociedad": "real sociedad", "ath bilbao": "athletic club", "ath madrid": "atletico madrid",
    "wolves": "wolverhampton wanderers", "nott'm forest": "nottingham forest",
    "sheffield united": "sheffield utd", "newcastle": "newcastle united",
    "leeds": "leeds united", "west ham": "west ham", "betis": "real betis",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = " ".join(s.lower().replace(".", " ").split())
    return ALIAS.get(s, s)


def _pick(cols, *cands):
    low = {c.lower(): c for c in cols}
    for cand in cands:
        if cand in low:
            return low[cand]
    for c in cols:
        for cand in cands:
            if cand in c.lower():
                return c
    return None


def main() -> None:
    us = sd.Understat(leagues=LEAGUES, seasons="2025")
    sched = us.read_schedule().reset_index()
    pm = us.read_player_match_stats().reset_index()
    shots = us.read_shot_events().reset_index()
    preds = json.loads((ROOT / "data" / "predictions.json").read_text(encoding="utf-8"))

    gcol = _pick(pm.columns, "game_id", "game")
    pcol = _pick(pm.columns, "player")
    tcol = _pick(pm.columns, "team")
    poscol = _pick(pm.columns, "position")
    mcol = _pick(pm.columns, "minutes", "time")
    goal = _pick(pm.columns, "goals")
    ast = _pick(pm.columns, "assists")
    xgc = _pick(pm.columns, "xg")
    xac = _pick(pm.columns, "xa")
    sgid = _pick(sched.columns, "game_id", "game")
    sh, sa, sdt = _pick(sched.columns, "home_team"), _pick(sched.columns, "away_team"), _pick(sched.columns, "date")

    # Minutes des buts : shot events avec result == "Goal", par (match, joueur)
    goal_min: dict[tuple, list[int]] = {}
    sgg, spg, smg, srg = (_pick(shots.columns, "game_id"), _pick(shots.columns, "player"),
                          _pick(shots.columns, "minute"), _pick(shots.columns, "result"))
    for _, r in shots[shots[srg] == "Goal"].iterrows():
        goal_min.setdefault((r[sgg], str(r[spg])), []).append(int(r[smg]))
    for k in goal_min:
        goal_min[k] = sorted(goal_min[k])

    sched = sched.copy()
    sched["day"] = pd.to_datetime(sched[sdt]).dt.strftime("%Y-%m-%d")
    game_info = {r[sgid]: (r[sh], r[sa]) for _, r in sched.iterrows()}
    key_to_game = {(r["day"], norm(r[sh]), norm(r[sa])): r[sgid] for _, r in sched.iterrows()}

    def _pair_substitutions(players: list[dict]) -> list[dict]:
        for player in players:
            player["display_pos"] = player["pos"]
            player["paired_with"] = None
            player["substitution_group"] = None
            player["pair_confidence"] = None

        by_team: dict[str, list[dict]] = {}
        for player in players:
            by_team.setdefault(player["team"], []).append(player)

        group_id = 1
        for team_players in by_team.values():
            outgoing = [p for p in team_players if p["off"] and p["smin"] is not None]
            incoming = [p for p in team_players if p["on"] and p["smin"] is not None]
            used_outgoing: set[int] = set()

            for entrant in sorted(incoming, key=lambda p: (p["smin"], p["player"])):
                best_idx, best_score = None, None
                for idx, leaver in enumerate(outgoing):
                    if idx in used_outgoing:
                        continue
                    minute_gap = abs(int(entrant["smin"]) - int(leaver["smin"]))
                    goalkeeper_penalty = 20 if POS_GROUP.get(leaver["pos"]) == "GK" else 0
                    score = minute_gap * 10 + goalkeeper_penalty
                    if best_score is None or score < best_score:
                        best_idx, best_score = idx, score

                if best_idx is None:
                    continue

                leaver = outgoing[best_idx]
                used_outgoing.add(best_idx)
                leaver["substitution_group"] = group_id
                leaver["paired_with"] = entrant["player"]
                entrant["substitution_group"] = group_id
                entrant["paired_with"] = leaver["player"]
                entrant["display_pos"] = leaver["pos"]
                entrant["pair_confidence"] = "good" if abs(int(entrant["smin"]) - int(leaver["smin"])) <= 2 else "minute_only"
                group_id += 1

            unpaired_incoming = [
                p for p in incoming
                if p["substitution_group"] is None and p["smin"] is not None
            ]
            fallback_outgoing = [
                p for p in team_players
                if not p["on"]
                and p["substitution_group"] is None
                and POS_GROUP.get(p["pos"]) != "GK"
            ]
            for entrant in sorted(unpaired_incoming, key=lambda p: (p["smin"], p["player"])):
                if not fallback_outgoing:
                    break
                leaver = min(
                    fallback_outgoing,
                    key=lambda p: (abs(POS_ORDER.get(p["pos"], 50) - 8), p["player"]),
                )
                fallback_outgoing.remove(leaver)
                leaver["off"] = True
                leaver["smin"] = entrant["smin"]
                leaver["substitution_group"] = group_id
                leaver["paired_with"] = entrant["player"]
                entrant["substitution_group"] = group_id
                entrant["paired_with"] = leaver["player"]
                entrant["display_pos"] = leaver["pos"]
                entrant["pair_confidence"] = "late_minute_inferred" if int(entrant["smin"]) >= 85 else "minute_inferred"
                group_id += 1

        display: list[dict] = []
        for team_players in by_team.values():
            starters = sorted(
                [p for p in team_players if not p["on"]],
                key=lambda p: (p["ord"], p["player"]),
            )
            entrants_by_group: dict[int, list[dict]] = {}
            unpaired_entrants = []
            for player in team_players:
                if not player["on"]:
                    continue
                group = player["substitution_group"]
                if group is None:
                    unpaired_entrants.append(player)
                else:
                    entrants_by_group.setdefault(group, []).append(player)

            for starter in starters:
                display.append(starter)
                group = starter["substitution_group"]
                if group is not None:
                    display.extend(sorted(entrants_by_group.get(group, []), key=lambda p: (p["smin"] or 0, p["player"])))
            display.extend(sorted(unpaired_entrants, key=lambda p: (p["smin"] or 0, p["player"])))
        return display

    def players_for(game_id):
        sub = pm[pm[gcol] == game_id]
        out = []
        for _, r in sub.iterrows():
            mins = int(r[mcol]) if pd.notna(r[mcol]) else 0
            if mins <= 0:
                continue
            pos = str(r[poscol]) if poscol and pd.notna(r[poscol]) else ""
            is_sub = pos.lower() == "sub"
            off = (not is_sub) and mins < 90
            smin = (90 - mins) if is_sub else (mins if off else None)
            out.append({
                "player": str(r[pcol]),
                "team": str(r[tcol]),
                "pos": pos,
                "display_pos": pos,
                "ord": POS_ORDER.get(pos, 50),
                "on": is_sub,
                "off": off,
                "smin": smin,
                "gmin": goal_min.get((game_id, str(r[pcol])), []),
                "g": int(r[goal]) if goal and pd.notna(r[goal]) else 0,
                "a": int(r[ast]) if ast and pd.notna(r[ast]) else 0,
                "xg": round(float(r[xgc]), 2) if xgc and pd.notna(r[xgc]) else 0.0,
                "xa": round(float(r[xac]), 2) if xac and pd.notna(r[xac]) else 0.0,
            })
        return _pair_substitutions(out)

    def find_game(m):
        gid = key_to_game.get((m["date"], norm(m["home"]), norm(m["away"])))
        if gid is not None:
            return gid
        for (day, nh, na), g in key_to_game.items():
            if day == m["date"] and (norm(m["home"]) in nh or nh in norm(m["home"])) \
               and (norm(m["away"]) in na or na in norm(m["away"])):
                return g
        return None

    # Compos limitées aux matchs les plus récents (Understat = saison courante ;
    # borne la taille du JSON chargé côté site).
    recent = sorted(preds["recent_matches"], key=lambda m: m["date"], reverse=True)[:200]
    lineups, matched, missing = {}, 0, []
    for m in recent:
        gid = find_game(m)
        if gid is None:
            missing.append(f"{m['date']} {m['home']}-{m['away']} (pas de match Understat)")
            continue
        hteam, ateam = game_info[gid]
        players = players_for(gid)
        if not players:
            missing.append(f"{m['date']} {m['home']}-{m['away']} (Understat sans stats joueurs)")
            continue
        motm = max(players, key=lambda p: p["g"] * 3 + p["a"] * 2 + p["xg"])
        for p in players:
            p["motm"] = (p["player"] == motm["player"] and p["team"] == motm["team"])
        lineups[f"{m['date']}|{m['home']}|{m['away']}"] = {
            "home": [p for p in players if p["team"] == hteam][:18],
            "away": [p for p in players if p["team"] == ateam][:18],
        }
        matched += 1

    OUT.write_text(json.dumps(lineups, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"lineups matched: {matched}/{len(recent)} matches -> {OUT.name}")
    if missing:
        print("not matched:")
        for x in missing:
            print("  -", x)


if __name__ == "__main__":
    main()
