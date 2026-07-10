"""
Stats joueurs Big Five complémentaires à team_power : cartons (Sofascore /incidents)
et % de passes réussies (agrégé depuis les fichiers player_match déjà scrapés).

Sortie data/bigfive_player_extra.json : { "norm(joueur)": {cards, yellow, red, pass_pct} }
+ clés "norm(joueur)|norm(équipe)" pour lever les homonymes. Chargé par le site et
fusionné dans le classement des joueurs Big Five.

Le scraping des cartons est RÉSUMABLE : chaque match est mis en cache (bigfive_cards_cache.json),
les relances reprennent où elles s'étaient arrêtées.
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

import ScraperFC as sfc
from ScraperFC.utils import botasaurus_browser_get_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "bigfive_player_extra.json"
CACHE = ROOT / "data" / "bigfive_cards_cache.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/bigfive_player_extra.json")
API = "https://api.sofascore.com/api/v1"
SEASON = "25/26"
LEAGUES = ["England Premier League", "Spain La Liga", "Italy Serie A", "Germany Bundesliga", "France Ligue 1"]
PM_FILES = [ROOT / "data" / "pl_player_match.json"] + sorted((ROOT / "data" / "player_match").glob("*.json"))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def load_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
    except Exception:
        return default


def scrape_cards(ss) -> dict:
    """Cartons par match, mis en cache. Retourne {match_id: [{player, team, cls}]}."""
    cache = load_json(CACHE, {})
    for league in LEAGUES:
        try:
            matches = ss.get_match_dicts(SEASON, league)
        except Exception as exc:
            print(f"  [{league}] liste KO : {exc}", file=sys.stderr)
            continue
        finished = [m for m in matches if str(m.get("status", {}).get("type", "")) == "finished"]
        print(f"[{league}] {len(finished)} matchs terminés")
        for i, m in enumerate(finished):
            mid = str(m["id"])
            if mid in cache:
                continue
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            try:
                inc = botasaurus_browser_get_json(f"{API}/event/{mid}/incidents").get("incidents", [])
            except Exception as exc:
                print(f"    incidents KO {mid}: {exc}", file=sys.stderr)
                continue
            cards = []
            for x in inc:
                if x.get("incidentType") == "card":
                    p = (x.get("player") or {}).get("name") or x.get("playerName")
                    if p:
                        cards.append({"player": p, "team": home if x.get("isHome") else away,
                                      "cls": x.get("incidentClass", "yellow")})
            cache[mid] = cards
            if (i + 1) % 25 == 0:
                CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"    {league}: {i+1}/{len(finished)}")
            time.sleep(0.25)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def aggregate_pass() -> dict:
    """% de passes réussies par joueur normalisé, depuis les player_match existants."""
    acc: dict[str, list[int]] = {}
    for f in PM_FILES:
        for r in load_json(f, []):
            ap, tp = r.get("acc_pass"), r.get("tot_pass")
            if ap is None or tp is None:
                continue
            k = norm(r.get("player", ""))
            if not k:
                continue
            a, t = acc.setdefault(k, [0, 0])
            acc[k] = [a + int(ap), t + int(tp)]
    return {k: round(100 * a / t, 1) for k, (a, t) in acc.items() if t > 0}


def main() -> int:
    ss = sfc.Sofascore()
    cache = scrape_cards(ss)

    # Agrège les cartons par joueur (et par joueur|équipe).
    by_player: dict[str, dict] = {}
    by_pt: dict[str, dict] = {}
    for events in cache.values():
        for e in events:
            red = e["cls"] in ("red", "yellowRed")
            for d in (by_player.setdefault(norm(e["player"]), {"cards": 0, "yellow": 0, "red": 0}),
                      by_pt.setdefault(f"{norm(e['player'])}|{norm(e['team'])}", {"cards": 0, "yellow": 0, "red": 0})):
                d["cards"] += 1
                d["red" if red else "yellow"] += 1

    pass_pct = aggregate_pass()

    extra: dict[str, dict] = {}
    for k, d in by_player.items():
        extra[k] = {**d, "pass_pct": pass_pct.get(k)}
    for k in pass_pct:
        extra.setdefault(k, {"cards": None, "yellow": None, "red": None})["pass_pct"] = pass_pct[k]
    for k, d in by_pt.items():
        pk = k.split("|")[0]
        extra[k] = {**d, "pass_pct": pass_pct.get(pk)}

    OUT.write_text(json.dumps(extra, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(by_player)} joueurs avec cartons, {len(pass_pct)} avec passe% -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
