"""
Fetch match lineups, player ratings and match events for World Cup 2026 from Sofascore.
Outputs data/worldcup_lineups.json which is loaded by WorldCupPredictions.jsx.

Améliorations :
- Postes réels (G/D/M/F -> GK/DC/MC/FW, 4 lignes) : la colonne `position` de
  scrape_player_match_stats est en double, on la déduplique.
- Formation par équipe (ex. 4-2-3-1).
- Événements via l'endpoint /incidents : minutes des buts (gmin), passes (amin),
  cartons (cards), et changements EXACTS (entrant/sortant/minute) -> appariement fiable.
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path
import pandas as pd
import ScraperFC as sfc
from ScraperFC.utils import botasaurus_browser_get_json

ROOT = Path(__file__).resolve().parents[1]
PREDS_PATH = ROOT / "data" / "predictions.json"
OUT = ROOT / "data" / "worldcup_lineups.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/worldcup_lineups.json")
API = "https://api.sofascore.com/api/v1"
SCHEMA = 3  # bump quand la structure change -> invalide le cache

POS_MAP = {"G": "GK", "D": "DC", "M": "MC", "F": "FW"}
POS_ORD = {"GK": 0, "DC": 1, "MC": 2, "FW": 3}
POS_GROUP = {"GK": "GK", "DC": "DEF", "MC": "MID", "FW": "ATT"}


def compute_note(group: str, g: int, a: int, xg: float, xa: float, conceded: int) -> float:
    """« Ma note » /10 calculée et consciente du poste (indépendante de la note Sofascore).

    Apport offensif pour tous ; gardiens et défenseurs valorisés/pénalisés selon les buts
    encaissés par leur équipe. Aligné sur le calcul du projet clubs.
    """
    off = 1.3 * g + 0.8 * a + 0.5 * xg + 0.5 * xa

    def csb(strong: float, weak: float) -> float:
        if conceded <= 0:
            return strong
        if conceded == 1:
            return weak
        if conceded == 2:
            return 0.0
        return -0.4 * (conceded - 2)

    if group == "GK":
        note = 6.4 + csb(1.4, 0.6) + 0.5 * off
    elif group == "DEF":
        note = 6.0 + csb(1.1, 0.4) + off
    elif group == "MID":
        note = 6.0 + off + csb(0.3, 0.1)
    else:
        note = 6.0 + off
    return round(min(10.0, max(3.5, note)), 1)


def to_int(val, default=0):
    if pd.isna(val) or val is None:
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def to_float(val, default=0.0):
    if pd.isna(val) or val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def to_bool(val, default=False):
    if pd.isna(val) or val is None:
        return default
    return bool(val)


def norm(name: str) -> str:
    """Normalisation des noms d'ÉQUIPES (avec alias pays)."""
    name = str(name).strip().lower()
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.replace("united states", "usa")
    name = name.replace("korea republic", "south korea")
    name = name.replace("czech republic", "czechia")
    name = name.replace("bosnia and herzegovina", "bosnia & herzegovina")
    name = name.replace("turkey", "turkiye")
    name = name.replace("cape verde", "cabo verde")
    name = name.replace("ivory coast", "cote d'ivoire")
    name = name.replace("&", "and")
    name = name.replace(" ", "")
    name = name.replace("-", "")
    return name


def pnorm(name: str) -> str:
    """Normalisation des noms de JOUEURS (accents/casse/espaces retirés)."""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return " ".join(name.lower().split())


def _events(match_id) -> dict:
    """Buts (min + passeur), cartons (min + type), changements exacts, par joueur normalisé."""
    try:
        data = botasaurus_browser_get_json(f"{API}/event/{match_id}/incidents")
    except Exception as exc:
        print(f"  incidents KO {match_id}: {exc}", file=sys.stderr)
        return {"gmin": {}, "amin": {}, "cards": {}, "subs": []}
    inc = data.get("incidents", []) if isinstance(data, dict) else []
    gmin: dict[str, list[int]] = {}
    amin: dict[str, list[int]] = {}
    cards: dict[str, list[dict]] = {}
    subs: list[dict] = []
    for x in inc:
        t = x.get("incidentType")
        minute = to_int(x.get("time"), 0)
        added = to_int(x.get("addedTime"), 0)
        disp = minute + added if added else minute
        if t == "goal":
            if x.get("goalType") != "own":
                scorer = x.get("player", {}).get("name")
                if scorer:
                    gmin.setdefault(pnorm(scorer), []).append(disp)
            a1 = x.get("assist1", {})
            if a1 and a1.get("name"):
                amin.setdefault(pnorm(a1["name"]), []).append(disp)
        elif t == "card":
            p = x.get("player", {}).get("name") or x.get("playerName")
            if p:
                cards.setdefault(pnorm(p), []).append({"min": disp, "type": x.get("incidentClass", "yellow")})
        elif t == "substitution":
            pin = x.get("playerIn", {}).get("name")
            pout = x.get("playerOut", {}).get("name")
            if pin and pout:
                subs.append({"in": pnorm(pin), "out": pnorm(pout), "min": disp})
    return {"gmin": gmin, "amin": amin, "cards": cards, "subs": subs}


def _formations(match_id) -> tuple[str | None, str | None]:
    try:
        lu = botasaurus_browser_get_json(f"{API}/event/{match_id}/lineups")
        return lu.get("home", {}).get("formation"), lu.get("away", {}).get("formation")
    except Exception:
        return None, None


def build_match(ss, match_id, h_norm):
    df = ss.scrape_player_match_stats(match_id)
    if df.empty:
        return None
    df = df.loc[:, ~df.columns.duplicated()]  # colonnes en double (position, jerseyNumber)
    ev = _events(match_id)
    form_h, form_a = _formations(match_id)

    max_rating, motm = -1.0, None
    for _, row in df.iterrows():
        r = to_float(row.get("rating"), 0.0)
        if r > max_rating:
            max_rating, motm = r, str(row.get("name"))

    home_players, away_players = [], []
    for _, row in df.iterrows():
        pname = str(row.get("name"))
        pteam = str(row.get("teamName"))
        key = pnorm(pname)
        mins = to_int(row.get("minutesPlayed"), 0)
        if mins <= 0:
            continue  # remplaçant non entré : exclu de la compo
        raw_pos = str(row.get("position", "M"))
        pos = POS_MAP.get(raw_pos, "MC")
        is_sub = to_bool(row.get("substitute"), False)

        pdata = {
            "player": pname, "team": pteam,
            "pos": pos, "display_pos": pos, "ord": POS_ORD.get(pos, 2),
            "on": is_sub and mins > 0, "off": False, "smin": None,
            "gmin": sorted(ev["gmin"].get(key, [])),
            "amin": sorted(ev["amin"].get(key, [])),
            "cards": ev["cards"].get(key, []),
            "g": to_int(row.get("goals"), 0),
            "a": to_int(row.get("goalAssist"), 0),
            "xg": round(to_float(row.get("expectedGoals"), 0.0), 2),
            "xa": round(to_float(row.get("expectedAssists"), 0.0), 2),
            "note": None,  # « ma note » calculée après le split par équipe (buts encaissés)
            "sofa": round(to_float(row.get("rating"), 6.0), 1),
            "paired_with": None, "substitution_group": None,
            "motm": pname == motm,
            "_mins": mins,
        }
        (home_players if norm(pteam) == h_norm else away_players).append(pdata)

    # « Ma note » consciente du poste : les buts encaissés = buts de l'équipe adverse.
    home_goals = sum(int(p["g"]) for p in home_players)
    away_goals = sum(int(p["g"]) for p in away_players)
    for p in home_players:
        p["note"] = compute_note(POS_GROUP.get(p["pos"], "ATT"), p["g"], p["a"], p["xg"], p["xa"], away_goals)
    for p in away_players:
        p["note"] = compute_note(POS_GROUP.get(p["pos"], "ATT"), p["g"], p["a"], p["xg"], p["xa"], home_goals)

    # Appariement EXACT des changements via les incidents.
    def apply_subs(players):
        idx = {pnorm(p["player"]): p for p in players}
        gid = 1
        for s in ev["subs"]:
            pin, pout = idx.get(s["in"]), idx.get(s["out"])
            if pin is None or pout is None:
                continue
            pout["off"], pout["smin"] = True, s["min"]
            pin["on"], pin["smin"] = True, s["min"]
            pin["display_pos"] = pout["pos"]
            pin["substitution_group"] = pout["substitution_group"] = gid
            pin["paired_with"], pout["paired_with"] = pout["player"], pin["player"]
            gid += 1

    apply_subs(home_players)
    apply_subs(away_players)

    def order(players):
        for p in players:
            p.pop("_mins", None)
        starters = sorted([p for p in players if not p["on"]], key=lambda p: (p["ord"], p["player"]))
        subs_by_group: dict[int, list[dict]] = {}
        loose: list[dict] = []
        for p in players:
            if not p["on"]:
                continue
            g = p["substitution_group"]
            if g is not None:
                subs_by_group.setdefault(g, []).append(p)
            else:
                loose.append(p)
        display = []
        for st in starters:
            display.append(st)
            g = st["substitution_group"]
            if g is not None:
                display.extend(subs_by_group.get(g, []))
        display.extend(sorted(loose, key=lambda p: (p["smin"] or 0, p["player"])))
        return display

    return {"home": order(home_players), "away": order(away_players),
            "formation_home": form_h, "formation_away": form_a}


def main() -> int:
    if not PREDS_PATH.exists():
        print(f"Predictions file not found: {PREDS_PATH}", file=sys.stderr)
        return 1
    preds = json.loads(PREDS_PATH.read_text(encoding="utf-8"))
    wc_matches = preds.get("wc_matches", [])
    if not wc_matches:
        print("No WC matches found in predictions.json", file=sys.stderr)
        return 1

    ss = sfc.Sofascore()
    print("Fetching FIFA World Cup 2026 matches list from Sofascore...")
    sofa_list = ss.get_match_dicts("2026", "FIFA World Cup")
    print(f"Found {len(sofa_list)} matches on Sofascore.")
    sofa_map = {}
    for m in sofa_list:
        h, a = norm(m["homeTeam"]["name"]), norm(m["awayTeam"]["name"])
        sofa_map[(h, a)] = m
        sofa_map[(a, h)] = m

    cache = {}
    if OUT.exists():
        try:
            cache = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass

    lineups, done = {}, 0
    for i, m in enumerate(wc_matches):
        mkey = f"{m['date']}|{m['home']}|{m['away']}"
        cached = cache.get(mkey)
        if cached and cached.get("schema") == SCHEMA:
            lineups[mkey] = cached
            done += 1
            continue
        h_norm, a_norm = norm(m["home"]), norm(m["away"])
        sofa_m = sofa_map.get((h_norm, a_norm))
        if not sofa_m:
            print(f"[{i+1}/{len(wc_matches)}] Not found on Sofascore: {m['home']} - {m['away']}")
            continue
        print(f"[{i+1}/{len(wc_matches)}] {m['home']} - {m['away']} (ID {sofa_m['id']})")
        try:
            built = build_match(ss, sofa_m["id"], h_norm)
            if built is None:
                print("  empty")
                continue
            built["schema"] = SCHEMA
            lineups[mkey] = built
            done += 1
            # écriture incrémentale (robustesse)
            OUT.write_text(json.dumps(lineups, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(0.4)
        except Exception as exc:
            print(f"  failed ID {sofa_m['id']}: {exc}", file=sys.stderr)
            continue

    OUT.write_text(json.dumps(lineups, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Scraped {done}/{len(wc_matches)} lineups -> {OUT.name}")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(lineups, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Copied to {SITE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
