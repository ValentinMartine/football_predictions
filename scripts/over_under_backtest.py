"""
Modèle de score (Poisson) + backtest du marché Over/Under 2.5 buts sur cotes réelles.

Deux régresseurs LightGBM (objectif Poisson) estiment les buts attendus domicile/extérieur
à partir des mêmes features. La somme suit une loi de Poisson -> P(plus de 2,5 buts).
On calibre P(Over) sur la validation, puis on parie contre la meilleure cote de clôture
(line shopping) le côté dont l'edge dépasse un seuil. On mesure ROI (clôture moyenne et
meilleure) + CLV (ouverture vs clôture).

But : tester si un marché "soft" (O/U) offre un edge là où le 1X2 n'en offre pas.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.stats import poisson
from sklearn.isotonic import IsotonicRegression

from src.modeling import temporal_split
from src.pipeline import FEATURE_COLS, build_features, load_matches

ROOT = Path(__file__).resolve().parents[1]
MIN_EDGE = 0.05
MIN_ODDS, MAX_ODDS = 1.5, 3.5
TOP5 = {"E0", "SP1", "I1", "D1", "F1"}


def _reg():
    return LGBMRegressor(objective="poisson", n_estimators=400, learning_rate=0.03,
                         max_depth=5, num_leaves=31, subsample=0.85, colsample_bytree=0.85,
                         min_child_samples=35, random_state=42, verbose=-1)


def _sim(df, p_over, over_col, under_col):
    """Backtest 2 issues (Over/Under 2.5) à quart de Kelly, cappé à 2 % de bankroll."""
    bankroll, peak, wins, staked, profit, n = 1000.0, 1000.0, 0, 0.0, 0.0, 0
    for i, r in enumerate(df.itertuples(index=False)):
        oo, uo = getattr(r, over_col), getattr(r, under_col)
        if not (np.isfinite(oo) and np.isfinite(uo) and oo > 1 and uo > 1):
            continue
        po, pu = p_over[i], 1 - p_over[i]
        eo, eu = po * oo - 1, pu * uo - 1
        over = eo >= eu
        prob, price, edge = (po, oo, eo) if over else (pu, uo, eu)
        if edge < MIN_EDGE or price < MIN_ODDS or price > MAX_ODDS:
            continue
        k = max(0.0, min((prob * price - 1) / (price - 1) * 0.25, 0.02))
        stake = bankroll * k
        if stake < 0.01:
            continue
        total = r.home_goals + r.away_goals
        won = (total >= 3) if over else (total <= 2)
        pl = stake * (price - 1) if won else -stake
        bankroll += pl
        peak = max(peak, bankroll)
        staked += stake
        profit += pl
        wins += int(won)
        n += 1
    roi = round(100 * profit / staked, 2) if staked else 0.0
    return {"n_bets": n, "roi_pct": roi, "win_rate_pct": round(100 * wins / n, 1) if n else 0.0,
            "final_bankroll": round(bankroll, 2)}


def main() -> int:
    raw = load_matches().reset_index(drop=True)
    feat = build_features().reset_index(drop=True)
    assert len(raw) == len(feat), "désalignement raw/features"

    feat["over_close"] = pd.to_numeric(raw.get("AvgC>2.5"), errors="coerce")
    feat["under_close"] = pd.to_numeric(raw.get("AvgC<2.5"), errors="coerce")
    feat["over_best"] = pd.to_numeric(raw.get("MaxC>2.5"), errors="coerce")
    feat["under_best"] = pd.to_numeric(raw.get("MaxC<2.5"), errors="coerce")
    feat["over_open"] = pd.to_numeric(raw.get("B365>2.5"), errors="coerce")

    train, val, test = temporal_split(feat)
    test = test.reset_index(drop=True)
    mh, ma = _reg().fit(train[FEATURE_COLS], train["home_goals"]), _reg().fit(train[FEATURE_COLS], train["away_goals"])

    def p_over(d):
        lam = np.clip(mh.predict(d[FEATURE_COLS]) + ma.predict(d[FEATURE_COLS]), 0.1, 8)
        return 1 - poisson.cdf(2, lam)   # P(total >= 3) = P(Over 2.5)

    # Calibration isotone de P(Over) sur la validation
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
    iso.fit(p_over(val), (val["home_goals"] + val["away_goals"] >= 3).astype(float))
    pt = np.clip(iso.transform(p_over(test)), 1e-4, 1 - 1e-4)

    over_hit = float((test["home_goals"] + test["away_goals"] >= 3).mean())
    closing = _sim(test, pt, "over_close", "under_close")
    best = _sim(test, pt, "over_best", "under_best")
    print(f"Test : {len(test)} matchs, {over_hit:.1%} de Over 2.5 réels")
    print(f"{'Prix':16}{'paris':>8}{'ROI %':>10}{'winrate':>10}")
    for name, s in [("clôture moyenne", closing), ("meilleure cote", best)]:
        print(f"{name:16}{s['n_bets']:>8}{s['roi_pct']:>10.2f}{s['win_rate_pct']:>10.1f}")

    # Découpage par niveau : top 5 vs divisions inférieures / autres (meilleure cote)
    is_top = test["league"].isin(TOP5).to_numpy()
    tiers = {}
    for tname, mask in [("top5", is_top), ("mineures", ~is_top)]:
        sub = test[mask].reset_index(drop=True)
        if len(sub) == 0:
            continue
        s = _sim(sub, pt[mask], "over_best", "under_best")
        tiers[tname] = s
        print(f"  [{tname:9}] meilleure cote : {s['n_bets']} paris, ROI {s['roi_pct']:+.2f}%, winrate {s['win_rate_pct']}%")

    # CLV : sur les paris Over sélectionnés à l'ouverture, cote ouverture vs clôture
    op, cl = pd.to_numeric(test["over_open"], errors="coerce").to_numpy(), pd.to_numeric(test["over_close"], errors="coerce").to_numpy()
    clv = [op[i] / cl[i] - 1 for i in range(len(test))
           if np.isfinite(op[i]) and np.isfinite(cl[i]) and op[i] > 1 and cl[i] > 1
           and pt[i] * op[i] - 1 >= MIN_EDGE and MIN_ODDS <= op[i] <= MAX_ODDS]
    mean_clv = round(100 * float(np.mean(clv)), 2) if clv else 0.0
    print(f"CLV moyenne (Over, ouverture vs clôture) : {mean_clv:+.2f}% sur {len(clv)} paris" if clv else "CLV : aucun pari")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": "Over/Under 2.5 buts",
        "model": "Score Poisson (2 régresseurs LightGBM), P(Over) calibrée (isotone)",
        "n_test": int(len(test)),
        "over_rate_pct": round(100 * over_hit, 1),
        "closing_avg": closing,
        "line_shopping": best,
        "by_tier": tiers,
        "mean_clv_pct": mean_clv,
        "clv_n_bets": len(clv),
        "note": ("Testé sur 19 championnats (dont divisions inférieures), ~13 500 matchs de test. "
                 "Aucun edge à la clôture. Le line shopping ramène près de l'équilibre sur le top 5 "
                 "(~0 %) mais reste négatif sur les ligues mineures (le modèle y est moins précis, "
                 "ce qui annule leur inefficience supposée). CLV positive mais jamais convertie en ROI. "
                 "Conclusion honnête : aucun profit fiable démontrable sur ces marchés publics."),
    }
    out = ROOT / "data" / "over_under_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    site = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/over_under_report.json")
    if site.parent.exists():
        site.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"écrit {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
