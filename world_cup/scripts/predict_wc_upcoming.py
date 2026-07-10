"""
Prédit les matchs WC à venir (issus de wc_odds.json) avec le modèle Elo+FIFA+forme+LightGBM
calibré, puis calcule l'edge du modèle contre le marché (line shopping = meilleure cote).

Enrichit wc_odds.json : probas calibrées du modèle, edge par issue, recommandation de pari.
C'est le test « données appliquées aux sélections vs marché » là où le marché est moins
efficient. Aucun edge garanti — on l'affiche honnêtement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import log_loss

from src.calibration import TemperatureScaling
from src.pipeline import FEATURE_COLS, build_features
from src.poisson import elo_lambdas, score_distribution

ROOT = Path(__file__).resolve().parents[1]
ODDS = ROOT / "data" / "wc_odds.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/wc_odds.json")
VAL_START = pd.Timestamp("2024-08-01")
# Bande d'edge plausible : un vrai edge est petit. Un edge énorme (>15 %) contre un marché
# à 25 books signifie que LE MODÈLE a tort, pas qu'il y a de la value.
EDGE_MIN, EDGE_MAX = 0.02, 0.15
LABELS = ["1", "N", "2"]

# Alias noms The Odds API -> results.csv (martj42) si besoin.
ALIAS = {"United States": "USA", "South Korea": "Korea Republic", "Turkey": "Türkiye"}


def _elo_probs(df, b, mu):
    out = np.zeros((len(df), 3))
    for i, ed in enumerate(df["elo_diff"].to_numpy()):
        lh, la = elo_lambdas(ed, b, mu)
        ph, pd_, pa, _ = score_distribution(lh, la)
        out[i] = [ph, pd_, pa]
    return out


def main() -> int:
    odds = json.loads(ODDS.read_text(encoding="utf-8"))
    fixtures = odds.get("matches", [])
    if not fixtures:
        print("Aucun match à venir dans wc_odds.json")
        return 0

    ef = pd.DataFrame([{
        "date": m["commence"][:10],
        "home_team": ALIAS.get(m["home"], m["home"]),
        "away_team": ALIAS.get(m["away"], m["away"]),
        "tournament": "FIFA World Cup",
        "city": "", "country": "United States", "neutral": True,
    } for m in fixtures])

    df = build_features(extra_fixtures=ef)
    played = df[~df["is_predict"]].copy()
    up = df[df["is_predict"]].copy().reset_index(drop=True)

    train = played[played["date"] < VAL_START]
    val = played[played["date"] >= VAL_START]

    ed, gd = train["elo_diff"].values, (train["home_score"] - train["away_score"]).values
    b = float((ed * gd).sum() / (ed * ed).sum())
    mu = float((train["home_score"] + train["away_score"]).mean())

    model = LGBMClassifier(n_estimators=400, learning_rate=0.03, max_depth=5, num_leaves=31,
                           subsample=0.8, colsample_bytree=0.8, min_child_samples=50,
                           random_state=42, verbose=-1)
    model.fit(train[FEATURE_COLS], train["outcome"])

    pe_val = _elo_probs(val, b, mu)
    pm_val = model.predict_proba(val[FEATURE_COLS])
    yv = val["outcome"].values
    w = float(min(np.linspace(0, 1, 21),
                  key=lambda x: log_loss(yv, x * pm_val + (1 - x) * pe_val, labels=[0, 1, 2])))
    calib = TemperatureScaling().fit(w * pm_val + (1 - w) * pe_val, yv)

    pe_up = _elo_probs(up, b, mu)
    pm_up = model.predict_proba(up[FEATURE_COLS])
    pbc = calib.transform(w * pm_up + (1 - w) * pe_up)

    for i, m in enumerate(fixtures):
        probs = [round(float(x), 3) for x in pbc[i]]
        best = m["best"]  # meilleures cotes [1, N, 2]
        edges = [round(probs[k] * best[k] - 1, 3) for k in range(3)]
        side = int(np.argmax(edges))
        model_fav = int(np.argmax(probs))
        market_fav = int(np.argmin([1 / o for o in best]))  # issue la plus probable au marché
        m["model_prob"] = probs
        m["edge"] = edges
        # value crédible seulement dans une bande d'edge plausible
        plausible = EDGE_MIN <= edges[side] <= EDGE_MAX
        m["bet"] = {
            "side": LABELS[side], "best_odds": best[side], "edge": edges[side],
            "plausible_value": plausible,
            "verdict": ("accord avec le marché" if model_fav == market_fav
                        else "désaccord, le marché est probablement juste"),
        }

    disagree = sum(1 for m in fixtures if "désaccord" in m["bet"]["verdict"])
    odds["model_note"] = (
        "Probabilités calibrées du modèle (Elo, FIFA, forme, LightGBM) comparées au marché "
        "(marge retirée). "
        f"Le modèle est en désaccord avec le marché sur {disagree}/{len(fixtures)} matchs et se "
        "montre moins tranché sur les favoris. Ses écarts élevés viennent de son imprécision, pas "
        "d'un avantage réel. Sur ce marché très suivi, le marché reste le meilleur estimateur. "
        "Aucun pari recommandé.")
    ODDS.write_text(json.dumps(odds, ensure_ascii=False, indent=2), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(odds, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"prédits {len(fixtures)} matchs :")
    for m in fixtures:
        print(f"  {m['home']} vs {m['away']}: modèle {m['model_prob']} vs marché {m['market_implied']} "
              f"-> {m['bet']['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
