"""Complète data/results.csv avec les résultats LIVE de Sofascore pour les matchs de la
Coupe du Monde 2026 que la source principale (martj42/international_results) n'a pas encore
publiés (elle a souvent plusieurs heures/jours de retard).

À exécuter juste après download_match_data.py et avant train_and_backtest : le bracket et
les prédictions reflètent alors les résultats dès qu'un match est terminé sur Sofascore.
Best-effort : si Sofascore est indisponible, le fichier reste inchangé.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results.csv"


def norm(name: str) -> str:
    name = str(name).strip().lower()
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    for a, b in [
        ("united states", "usa"), ("korea republic", "south korea"),
        ("czech republic", "czechia"), ("turkey", "turkiye"), ("cape verde", "cabo verde"),
        ("ivory coast", "cote d'ivoire"), ("ir iran", "iran"), ("china pr", "china"),
    ]:
        name = name.replace(a, b)
    return name.replace("&", "and").replace("-", "").replace(" ", "")


def main() -> int:
    try:
        import ScraperFC as sfc
        sofa = sfc.Sofascore()
        matches = sofa.get_match_dicts("2026", "FIFA World Cup")
    except Exception as exc:  # noqa: BLE001
        print(f"Sofascore indisponible, results.csv inchangé : {exc}")
        return 0

    scores: dict[tuple[str, str], tuple[int, int]] = {}
    for m in matches:
        if m.get("status", {}).get("type") != "finished":
            continue
        ht = m.get("homeTeam", {}).get("name")
        at = m.get("awayTeam", {}).get("name")
        hs = m.get("homeScore", {}).get("current")
        as_ = m.get("awayScore", {}).get("current")
        if ht is None or at is None or hs is None or as_ is None:
            continue
        scores[(norm(ht), norm(at))] = (int(hs), int(as_))

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
        print(f"  {df.at[idx, 'date']} {h} {hs}-{as_} {a} (Sofascore)")

    if patched:
        df.to_csv(RESULTS, index=False)
    print(f"patch_wc_results : {patched} match(s) complété(s) depuis Sofascore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
