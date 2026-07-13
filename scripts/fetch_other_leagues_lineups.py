"""Compositions + notes des matchs récents des autres championnats, via Sofascore (ScraperFC).

Pour chaque championnat couvert par Sofascore, récupère les N derniers matchs terminés
de la saison courante avec la composition des deux équipes : poste, buts/passes, xG/xA,
note Sofascore et « ma note » calculée (consciente du poste, comme le reste du projet).

Sortie : data/other_leagues_lineups.json, consommé par l'onglet « Autres championnats ».
Best-effort (scraping) : les ligues en échec sont simplement ignorées.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "other_leagues_lineups.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/other_leagues_lineups.json")
N_MATCHES = 8

# code division (build_other_leagues) -> nom de ligue ScraperFC/Sofascore
LEAGUE_MAP = {
    "E1": "England EFL Championship", "F2": "France Ligue 2", "D2": "Germany 2.Bundesliga",
    "I2": "Italy Serie B", "SP2": "Spain La Liga 2", "N1": "Netherlands Eredivisie",
    "P1": "Portugal Primeira Liga", "T1": "Turkiye Super Lig", "ARG": "Argentina Liga Profesional",
    "MEX": "Mexico Liga MX Apertura", "USA": "USA MLS", "SAU": "Saudi Arabia Pro League",
    "UKR": "Ukraine Premier League",
}
POS_MAP = {"G": "GK", "D": "DC", "M": "MC", "F": "FW"}
POS_GROUP = {"GK": "GK", "DC": "DEF", "MC": "MID", "FW": "ATT"}
POS_ORD = {"GK": 0, "DC": 1, "MC": 2, "FW": 3}


def _f(v, default=0.0):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


# Colonnes Sofascore par match -> clés compactes stockées par joueur.
EXTRA_STATS = {
    "saves": "sv", "goalsPrevented": "gp", "penaltySave": "ps",
    "wonTackle": "tw", "interceptionWon": "itc", "totalClearance": "clr",
    "blockedScoringAttempt": "blk", "outfielderBlock": "oblk",
    "duelWon": "dw", "duelLost": "dl", "aerialWon": "aw",
    "errorLeadToAShot": "els", "keyPass": "kp",
    "bigChanceCreated": "bcc", "bigChanceMissed": "bcm",
}


def compute_note(group, p, conceded):
    """« Ma note » v2 /10 : poste, minutes, actions individuelles (voir fetch_wc_lineups)."""
    mins = p.get("mins", 90) or 90
    w = min(1.0, max(0.2, mins / 90.0))
    off = (1.3 * p.get("g", 0) + 0.8 * p.get("a", 0) + 0.4 * p.get("xg", 0.0) + 0.4 * p.get("xa", 0.0)
           + 0.3 * p.get("bcc", 0) + 0.12 * p.get("kp", 0) - 0.3 * p.get("bcm", 0))
    dact = min(1.5, 0.09 * (p.get("tw", 0) + p.get("itc", 0))
               + 0.05 * (p.get("clr", 0) + p.get("blk", 0) + p.get("oblk", 0))
               + 0.04 * (p.get("dw", 0) - p.get("dl", 0)) + 0.04 * p.get("aw", 0))
    errors = -0.7 * p.get("els", 0)

    def csb(strong, weak):
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
                + w * csb(0.6, 0.25) + 0.4 * off + errors)
    elif group == "DEF":
        note = 6.0 + off + w * dact + w * csb(0.8, 0.3) + errors
    elif group == "MID":
        note = 6.0 + off + w * 0.6 * dact + w * csb(0.25, 0.1) + errors
    else:
        note = 6.0 + off + w * 0.3 * dact + errors
    return round(min(10.0, max(3.0, note)), 1)


RATINGS = ROOT / "data" / "other_leagues_ratings.json"
SITE_RATINGS = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/other_leagues_ratings.json")


def load_ratings() -> dict:
    """Magasin cumulatif des notes saison (dédupliqué par id de match Sofascore)."""
    if RATINGS.exists():
        try:
            return json.loads(RATINGS.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"seen": {}, "players": {}, "teams": {}}


def save_ratings(store: dict) -> None:
    blob = json.dumps(store, ensure_ascii=False)
    RATINGS.write_text(blob, encoding="utf-8")
    if SITE_RATINGS.parent.exists():
        SITE_RATINGS.write_text(blob, encoding="utf-8")


def update_ratings(store: dict, code: str, lname: str, flag: str, season, match_id,
                   home: str, away: str, hs, as_, home_players: list, away_players: list) -> bool:
    """Intègre un match au magasin (retourne False s'il y était déjà)."""
    seen = store["seen"].setdefault(code, [])
    if match_id in seen:
        return False
    seen.append(match_id)
    season = str(season or "")
    for team, opp_goals, own_goals, plist in ((home, as_, hs, home_players), (away, hs, as_, away_players)):
        if not team:
            continue
        tk = f"{team}|{code}|{season}"
        t = store["teams"].setdefault(tk, {"team": team, "league": lname, "flag": flag,
                                           "season": season,
                                           "power_sum": 0.0, "m": 0, "win": 0, "draw": 0, "loss": 0,
                                           "gf": 0, "ga": 0, "sofa_power_sum": 0.0, "sm": 0})
        notes = [p["note"] for p in plist if isinstance(p.get("note"), (int, float))]
        if notes:
            t["power_sum"] += sum(notes) * (11.0 / len(notes))
            t["m"] += 1
        sofas = [p["sofa"] for p in plist if isinstance(p.get("sofa"), (int, float)) and p["sofa"] > 0]
        if sofas:
            t["sofa_power_sum"] = t.get("sofa_power_sum", 0.0) + sum(sofas) * (11.0 / len(sofas))
            t["sm"] = t.get("sm", 0) + 1
        if isinstance(own_goals, int) and isinstance(opp_goals, int):
            t["gf"] += own_goals
            t["ga"] += opp_goals
            if own_goals > opp_goals:
                t["win"] += 1
            elif own_goals == opp_goals:
                t["draw"] += 1
            else:
                t["loss"] += 1
        for p in plist:
            pk = f"{p['player']}|{team}|{code}|{season}"
            a = store["players"].setdefault(pk, {"player": p["player"], "team": team,
                                                 "league": lname, "flag": flag,
                                                 "season": season,
                                                 "pos_counts": {},
                                                 "note_sum": 0.0, "n": 0, "g": 0, "a": 0,
                                                 "xg": 0.0, "xa": 0.0, "sofa_sum": 0.0, "sofa_n": 0})
            pos = p.get("display_pos") or p.get("pos")
            if pos:
                a.setdefault("pos_counts", {})[pos] = a.setdefault("pos_counts", {}).get(pos, 0) + 1
                a["pos"] = max(a["pos_counts"].items(), key=lambda item: item[1])[0]
            if isinstance(p.get("note"), (int, float)):
                a["note_sum"] += p["note"]
                a["n"] += 1
            if isinstance(p.get("sofa"), (int, float)) and p["sofa"] > 0:
                a["sofa_sum"] += p["sofa"]
                a["sofa_n"] += 1
            a["g"] += int(p.get("g") or 0)
            a["a"] += int(p.get("a") or 0)
            a["xg"] += float(p.get("xg") or 0.0)
            a["xa"] += float(p.get("xa") or 0.0)
    return True


def _div_meta():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bol", ROOT / "scripts" / "build_other_leagues.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DIV


def _players_from_stats(ps, team_home, team_away):
    """Construit les listes home/away depuis le DataFrame player-match Sofascore."""
    # Sofascore renvoie des colonnes en double (dont deux "position") : on garde la
    # première occurrence, sinon r.get("position") renvoie une Series et le poste
    # retombe sur le défaut "MC" (tous les joueurs milieux, gardiens inclus).
    ps = ps.loc[:, ~ps.columns.duplicated()]
    home, away = [], []
    for _, r in ps.iterrows():
        mins = int(_f(r.get("minutesPlayed"), 0))
        if mins <= 0:
            continue
        pos = POS_MAP.get(str(r.get("position", "M")), "MC")
        rating = round(_f(r.get("rating"), 6.0), 1)
        pdata = {
            "player": str(r.get("name")),
            "team": str(r.get("teamName")),
            "pos": pos, "display_pos": pos, "ord": POS_ORD.get(pos, 2),
            "g": int(_f(r.get("goals"), 0)), "a": int(_f(r.get("goalAssist"), 0)),
            "xg": round(_f(r.get("expectedGoals"), 0.0), 2),
            "xa": round(_f(r.get("expectedAssists"), 0.0), 2),
            "note": None, "sofa": rating, "mins": mins,
        }
        # Stats brutes Sofascore (composantes de la note v2, gardées pour recalibrage).
        for col, short in EXTRA_STATS.items():
            v = _f(r.get(col), 0.0)
            if v:
                pdata[short] = round(v, 2) if col == "goalsPrevented" else int(v)
        (home if pdata["team"] == team_home else away).append(pdata)
    hg = sum(p["g"] for p in home)
    ag = sum(p["g"] for p in away)
    for p in home:
        p["note"] = compute_note(POS_GROUP.get(p["pos"], "ATT"), p, ag)
    for p in away:
        p["note"] = compute_note(POS_GROUP.get(p["pos"], "ATT"), p, hg)
    home.sort(key=lambda p: p["ord"])
    away.sort(key=lambda p: p["ord"])
    return home[:18], away[:18]


def main() -> int:
    import ScraperFC as sfc
    sofa = sfc.Sofascore()
    DIV = _div_meta()
    # Reprise : on repart du fichier existant (le scraper peut crasher en cours).
    out = {}
    if OUT.exists():
        try:
            out = json.loads(OUT.read_text(encoding="utf-8")).get("leagues", {})
        except Exception:
            out = {}
    # Argument optionnel : ne traiter qu'un seul code de ligue (isolation par processus).
    only = sys.argv[1] if len(sys.argv) > 1 else None
    targets = {only: LEAGUE_MAP[only]} if only in LEAGUE_MAP else LEAGUE_MAP
    ratings_store = load_ratings()
    for code, league in targets.items():
        if code in out:
            print(f"  {code}: déjà présent, ignoré", flush=True)
            continue
        name, flag = DIV.get(code, (league, "🏳️"))
        try:
            seasons = sofa.get_valid_seasons(league)
            season = None
            matches = []
            for yr in list(seasons.keys() if isinstance(seasons, dict) else seasons):
                ms = sofa.get_match_dicts(yr, league)
                done = [m for m in ms if m.get("status", {}).get("type") == "finished"]
                if done:
                    season, matches = yr, done
                    break
            if not matches:
                print(f"  {code} {league}: aucun match terminé")
                continue
            matches = sorted(matches, key=lambda m: m.get("startTimestamp", 0))[-N_MATCHES:][::-1]
            league_matches = []
            for m in matches:
                ht = m.get("homeTeam", {}).get("name")
                at = m.get("awayTeam", {}).get("name")
                hs = m.get("homeScore", {}).get("current")
                as_ = m.get("awayScore", {}).get("current")
                try:
                    ps = sofa.scrape_player_match_stats(m["id"])
                except Exception as exc:
                    print(f"    match {m.get('id')} ignoré: {exc}")
                    continue
                home, away = _players_from_stats(ps, ht, at)
                if not home and not away:
                    continue
                update_ratings(ratings_store, code, name, flag, season, m.get("id"), ht, at, hs, as_, home, away)
                date = datetime.fromtimestamp(m.get("startTimestamp", 0), tz=timezone.utc).strftime("%Y-%m-%d")
                league_matches.append({
                    "date": date, "season": str(season), "home": ht, "away": at,
                    "score": f"{hs}-{as_}" if hs is not None else None,
                    "home_lineup": home, "away_lineup": away,
                })
            if league_matches:
                out[code] = {"code": code, "name": name, "flag": flag, "season": season, "matches": league_matches}
                print(f"  {code} {league}: {len(league_matches)} matchs avec compos", flush=True)
                _write(out)  # sauvegarde incrémentale : progression conservée si interruption
                save_ratings(ratings_store)
        except Exception as exc:
            print(f"  {code} {league}: échec ({exc})", flush=True)
            continue

    _write(out)
    total = sum(len(l["matches"]) for l in out.values())
    print(f"Terminé : {len(out)} championnats, {total} matchs avec compos -> {OUT.name}", flush=True)
    return 0


def _write(out: dict) -> None:
    payload = {
        "source": "Sofascore (ScraperFC)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leagues": out,
    }
    blob = json.dumps(payload, ensure_ascii=False, indent=1)
    OUT.write_text(blob, encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(blob, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
