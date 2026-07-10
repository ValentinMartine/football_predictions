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


def player_note(group: str, g: int, a: int, xg: float, xa: float, conceded: int) -> float:
    """« Ma note » /10 consciente du poste.

    Tous les joueurs sont crédités de leur apport offensif ; gardiens et défenseurs
    reçoivent en plus une composante défensive fondée sur les buts encaissés par leur
    équipe (clean sheet valorisé, encaissements pénalisés). Corrige le fait que la
    formule purement offensive laissait défenseurs et gardiens à ~6,0.
    """
    off = 1.3 * g + 0.8 * a + 0.5 * xg + 0.5 * xa

    def clean_sheet_bonus(strong: float, weak: float) -> float:
        if conceded <= 0:
            return strong
        if conceded == 1:
            return weak
        if conceded == 2:
            return 0.0
        return -0.4 * (conceded - 2)

    if group == "GK":
        note = 6.4 + clean_sheet_bonus(1.4, 0.6) + 0.5 * off
    elif group == "DEF":
        note = 6.0 + clean_sheet_bonus(1.1, 0.4) + off
    elif group == "MID":
        note = 6.0 + off + clean_sheet_bonus(0.3, 0.1)
    else:  # ATT, SUB, poste inconnu : purement offensif
        note = 6.0 + off
    return round(min(10.0, max(3.5, note)), 1)


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
    ev_path = ROOT / "data" / "match_events.json"
    match_events = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else {}

    # Notes Sofascore par match (PL + autres ligues scrapées) : index (home, away) -> {joueur: note}
    sofa_index: dict[tuple, dict] = {}
    sofa_files = [ROOT / "data" / "pl_player_match.json"] + sorted((ROOT / "data" / "player_match").glob("*.json")) \
        if (ROOT / "data" / "player_match").exists() else [ROOT / "data" / "pl_player_match.json"]
    for sf in sofa_files:
        if not sf.exists():
            continue
        for r in json.loads(sf.read_text(encoding="utf-8")):
            if r.get("rating"):
                sofa_index.setdefault((norm(r["home"]), norm(r["away"])), {})[norm(r["player"])] = round(float(r["rating"]), 1)

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

        return _display_order(players)

    def _display_order(players: list[dict]) -> list[dict]:
        """Titulaires triés par poste ; chaque remplaçant affiché juste sous le joueur
        qu'il remplace (via substitution_group)."""
        by_team: dict[str, list[dict]] = {}
        for player in players:
            by_team.setdefault(player["team"], []).append(player)
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

    def _factual_pairing(players: list[dict], ev: dict) -> list[dict]:
        """Appariement factuel via les événements FBref (entrant/sortant + minute)."""
        import re

        def clean_name(name: str) -> str:
            name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
            name = name.lower()
            name = re.sub(r'[^a-z0-9\s]', '', name)
            return " ".join(name.split())

        # Save original Understat sub info before resetting
        original_sub_info = {}
        for p in players:
            original_sub_info[p["player"]] = {
                "on": p["on"],
                "off": p["off"],
                "smin": p["smin"]
            }

        for p in players:
            p["display_pos"] = p["pos"]
            p["paired_with"] = None
            p["substitution_group"] = None
            p["pair_confidence"] = None
            if not p["on"]:
                p["off"] = False   # les faits fixeront les sorties
                p["smin"] = None

        # Build index for all players in this match
        idx = {}
        for p in players:
            c_name = clean_name(p["player"])
            idx[c_name] = p
            parts = c_name.split()
            if len(parts) > 1:
                idx[f"{parts[0]} {parts[-1]}"] = p
                surname_key = parts[-1]
                if surname_key not in idx:
                    idx[surname_key] = p
                else:
                    idx[surname_key] = "AMBIGUOUS"

        def find_player(raw_name: str):
            if not raw_name:
                return None
            c_name = clean_name(raw_name)
            if c_name in idx:
                p = idx[c_name]
                if p != "AMBIGUOUS":
                    return p
            parts = c_name.split()
            if len(parts) > 1:
                fl_name = f"{parts[0]} {parts[-1]}"
                if fl_name in idx:
                    p = idx[fl_name]
                    if p != "AMBIGUOUS":
                        return p
                if parts[-1] in idx:
                    p = idx[parts[-1]]
                    if p != "AMBIGUOUS":
                        return p
            return None

        gid = 1
        for s in ev.get("subs", []):
            pin = find_player(s.get("in", ""))
            pout = find_player(s.get("out", ""))
            minute = s.get("minute")
            if pin is not None:
                pin["on"] = True
                pin["smin"] = minute
                pin["off"] = False
            if pout is not None:
                pout["off"] = True
                pout["on"] = False
                pout["smin"] = minute
            if pin is not None and pout is not None:
                pin["paired_with"] = pout["player"]
                pout["paired_with"] = pin["player"]
                pin["display_pos"] = pout["pos"]
                pin["substitution_group"] = gid
                pout["substitution_group"] = gid
                pin["pair_confidence"] = pout["pair_confidence"] = "fbref"
                gid += 1

        # Fallback: restore off state and minutes from original Understat for those who went off but weren't matched
        for p in players:
            if not p["on"] and not p["off"] and original_sub_info.get(p["player"], {}).get("off", False):
                orig = original_sub_info[p["player"]]
                p["off"] = True
                p["smin"] = orig["smin"]

        # Now pair remaining unmatched incoming/outgoing players using Understat minutes
        unmatched_in = [p for p in players if p["on"] and p["paired_with"] is None and p["smin"] is not None]
        unmatched_out = [p for p in players if not p["on"] and p["off"] and p["paired_with"] is None]

        for entrant in sorted(unmatched_in, key=lambda p: (p["smin"] or 999, p["player"])):
            best_idx, best_score = None, None
            team_out = [p for p in unmatched_out if p["team"] == entrant["team"] and p["paired_with"] is None]
            for i, leaver in enumerate(team_out):
                orig = original_sub_info.get(leaver["player"], {})
                orig_smin = orig.get("smin")
                if orig_smin is None:
                    continue
                minute_gap = abs(int(entrant["smin"]) - int(orig_smin))
                if best_score is None or minute_gap < best_score:
                    best_idx, best_score = i, minute_gap
            if best_idx is not None and best_score is not None and best_score <= 5:
                leaver = team_out[best_idx]
                leaver["paired_with"] = entrant["player"]
                leaver["substitution_group"] = gid
                entrant["paired_with"] = leaver["player"]
                entrant["display_pos"] = leaver["pos"]
                entrant["substitution_group"] = gid
                entrant["pair_confidence"] = "fbref_fallback"
                leaver["pair_confidence"] = "fbref_fallback"
                gid += 1

        goal_by_player: dict[str, list[int]] = {}
        for g in ev.get("goals", []):
            if g.get("minute") is not None:
                goal_by_player.setdefault(norm(g.get("scorer", "")), []).append(int(g["minute"]))
        for p in players:
            gm = goal_by_player.get(norm(p["player"]))
            if gm:
                p["gmin"] = sorted(gm)
        return _display_order(players)

    def players_for(game_id, ev=None):
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
            g_ = int(r[goal]) if goal and pd.notna(r[goal]) else 0
            a_ = int(r[ast]) if ast and pd.notna(r[ast]) else 0
            xg_ = round(float(r[xgc]), 2) if xgc and pd.notna(r[xgc]) else 0.0
            xa_ = round(float(r[xac]), 2) if xac and pd.notna(r[xac]) else 0.0
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
                "g": g_, "a": a_, "xg": xg_, "xa": xa_,
            })
        # « Ma note » consciente du poste : les buts encaissés = buts de l'équipe adverse.
        team_goals: dict[str, int] = {}
        for p in out:
            team_goals[p["team"]] = team_goals.get(p["team"], 0) + int(p["g"])
        total_goals = sum(team_goals.values())
        for p in out:
            conceded = total_goals - team_goals.get(p["team"], 0)
            p["note"] = player_note(POS_GROUP.get(p["pos"], "ATT"), p["g"], p["a"], p["xg"], p["xa"], conceded)
        # Faits FBref si disponibles (entrant/sortant exacts), sinon appariement inféré.
        if ev and ev.get("subs"):
            return _factual_pairing(out, ev)
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
        mkey = f"{m['date']}|{m['home']}|{m['away']}"
        players = players_for(gid, match_events.get(mkey))
        if not players:
            missing.append(f"{m['date']} {m['home']}-{m['away']} (Understat sans stats joueurs)")
            continue
        motm = max(players, key=lambda p: p["g"] * 3 + p["a"] * 2 + p["xg"])
        srow = sofa_index.get((norm(m["home"]), norm(m["away"])), {})
        for p in players:
            p["motm"] = (p["player"] == motm["player"] and p["team"] == motm["team"])
            sofa = srow.get(norm(p["player"]))
            if sofa is not None:
                p["sofa"] = sofa
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
