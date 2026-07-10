"""
Récupère les cotes 1/N/2 des matchs à venir de la Coupe du Monde via The Odds API
(clé lue depuis .env.local ou la variable d'environnement THE_ODDS_API_KEY).

Pour chaque match : cote moyenne et meilleure (line shopping) par issue, plus les
probabilités implicites du marché (marge retirée). Écrit data/wc_odds.json.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "wc_odds.json"
SPORT = "soccer_fifa_world_cup"


def _load_key() -> str | None:
    key = os.environ.get("THE_ODDS_API_KEY")
    if key:
        return key
    env = ROOT / ".env.local"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("THE_ODDS_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def main() -> int:
    key = _load_key()
    if not key:
        print("Pas de clé The Odds API (THE_ODDS_API_KEY ou .env.local).", file=sys.stderr)
        return 1
    url = (f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds/"
           f"?apiKey={key}&regions=eu,uk&markets=h2h&oddsFormat=decimal")
    with urllib.request.urlopen(url, timeout=30) as r:
        remaining = r.headers.get("x-requests-remaining")
        data = json.load(r)

    matches = []
    for m in data:
        home, away = m["home_team"], m["away_team"]
        # agrège les cotes de tous les books : max (meilleure) et moyenne par issue
        acc = {home: [], "Draw": [], away: []}
        for bk in m.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk["key"] != "h2h":
                    continue
                for o in mk["outcomes"]:
                    if o["name"] in acc:
                        acc[o["name"]].append(float(o["price"]))
        if not all(acc[k] for k in (home, "Draw", away)):
            continue
        avg = [round(sum(acc[k]) / len(acc[k]), 3) for k in (home, "Draw", away)]
        best = [round(max(acc[k]), 3) for k in (home, "Draw", away)]
        raw = [1 / o for o in avg]
        s = sum(raw)
        implied = [round(x / s, 3) for x in raw]  # marge retirée
        matches.append({
            "home": home, "away": away, "commence": m["commence_time"],
            "n_books": len(m.get("bookmakers", [])),
            "avg": avg, "best": best, "market_implied": implied,
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "The Odds API (soccer_fifa_world_cup, h2h, regions eu/uk)",
        "quota_remaining": remaining,
        "matches": matches,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"écrit {len(matches)} matchs -> {OUT.name} (quota restant: {remaining})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
