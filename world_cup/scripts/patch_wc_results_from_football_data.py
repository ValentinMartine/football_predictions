"""Complète data/results.csv avec les résultats de l'API football-data.org (palier
gratuit, Coupe du Monde incluse) pour les matchs que martj42 n'a pas encore publiés.

Contrairement à Sofascore (navigateur, bloqué depuis les IP GitHub), c'est une API HTTP
simple qui fonctionne en CI : c'est elle qui rend le site « live » quand le PC est éteint.

Token : variable d'environnement FOOTBALL_DATA_API_TOKEN (inscription gratuite sur
https://www.football-data.org/client/register). Sans token, le script ne fait rien.
"""
from __future__ import annotations

import json
import os
import unicodedata
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results.csv"
API = "https://api.football-data.org/v4/competitions/WC/matches?status=FINISHED"


def norm(name: str) -> str:
    name = str(name).strip().lower()
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    for a, b in [
        ("united states", "usa"), ("korea republic", "south korea"),
        ("czech republic", "czechia"), ("turkey", "turkiye"), ("cape verde", "cabo verde"),
        ("ivory coast", "cote d'ivoire"), ("ir iran", "iran"), ("china pr", "china"),
        ("bosnia and herzegovina", "bosnia"), ("bosnia & herzegovina", "bosnia"),
    ]:
        name = name.replace(a, b)
    return name.replace("&", "and").replace("-", "").replace(" ", "")


def main() -> int:
    token = os.environ.get("FOOTBALL_DATA_API_TOKEN", "").strip()
    if not token:
        print("FOOTBALL_DATA_API_TOKEN absent : patch football-data ignoré.")
        return 0

    req = urllib.request.Request(API, headers={"X-Auth-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"football-data.org indisponible, results.csv inchangé : {exc}")
        return 0

    scores: dict[tuple[str, str], tuple[int, int]] = {}
    for m in data.get("matches", []):
        ht = (m.get("homeTeam") or {}).get("name")
        at = (m.get("awayTeam") or {}).get("name")
        ft = (m.get("score") or {}).get("fullTime") or {}
        hs, as_ = ft.get("home"), ft.get("away")
        if ht is None or at is None or hs is None or as_ is None:
            continue
        scores[(norm(ht), norm(at))] = (int(hs), int(as_))
    print(f"football-data.org : {len(scores)} match(s) terminés récupérés.")

    df = pd.read_csv(RESULTS)
    df["home_score"] = df["home_score"].astype("Int64")
    df["away_score"] = df["away_score"].astype("Int64")
    mask = (df["tournament"] == "FIFA World Cup") & (df["date"] >= "2026-06-01") & (df["home_score"].isna())
    patched = 0
    for idx in df[mask].index:
        h, a = df.at[idx, "home_team"], df.at[idx, "away_team"]
        key, rev = (norm(h), norm(a)), (norm(a), norm(h))
        if key in scores:
            hs, as_ = scores[key]
        elif rev in scores:
            as_, hs = scores[rev]
        else:
            continue
        df.at[idx, "home_score"] = hs
        df.at[idx, "away_score"] = as_
        patched += 1
        print(f"  {df.at[idx, 'date']} {h} {hs}-{as_} {a} (football-data)")

    if patched:
        df.to_csv(RESULTS, index=False)
    print(f"patch_wc_results_from_football_data : {patched} match(s) complété(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
