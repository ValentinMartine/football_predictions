"""
Backtest CLV (closing line value) / line shopping sur le test tenu à l'écart.

Rejoue les paris du modèle (probas calibrées) à trois niveaux de prix, tous issus des
CSV football-data.co.uk locaux :
  - clôture moyenne  (référence actuelle du modèle),
  - ouverture        (parier tôt : capte la value avant correction du marché),
  - meilleure cote   (line shopping : meilleure cote de clôture parmi les books).

Mesure aussi la CLV moyenne des paris sélectionnés à l'ouverture : cote_ouverture /
cote_clôture − 1. Une CLV moyenne > 0 = edge réel (le marché se déplace en notre faveur),
détectable avec beaucoup moins de paris qu'un ROI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.backtesting import ROBUST_POLICY, simulate
from src.calibration import TemperatureScaling
from src.modeling import elo_probabilities, fit_lgbm, temporal_split, tune_blend
from src.pipeline import FEATURE_COLS, build_features

OUT = Path(__file__).resolve().parents[1] / "data" / "clv_report.json"
POLICY = {k: ROBUST_POLICY[k] for k in ("threshold", "min_edge", "min_odds", "max_odds")}
ARGS = dict(min_confidence=POLICY["threshold"], min_edge=POLICY["min_edge"],
            min_odds=POLICY["min_odds"], max_odds=POLICY["max_odds"])


def _priced(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    d = df.copy()
    for side in ("home", "draw", "away"):
        d[f"odds_{side}"] = pd.to_numeric(d[f"{prefix}_{side}"], errors="coerce")
    return d


def _mean_clv(df: pd.DataFrame, probs: np.ndarray) -> tuple[float, int]:
    """CLV moyenne des paris sélectionnés à l'ouverture (cote ouverture vs clôture)."""
    op = df[["open_home", "open_draw", "open_away"]].apply(pd.to_numeric, errors="coerce").to_numpy()
    cl = df[["close_home", "close_draw", "close_away"]].apply(pd.to_numeric, errors="coerce").to_numpy()
    clvs = []
    for i in range(len(df)):
        if not (np.isfinite(op[i]).all() and np.isfinite(cl[i]).all() and (op[i] > 1).all()):
            continue
        side = int(np.argmax(probs[i] * op[i] - 1))
        prob, price = float(probs[i, side]), float(op[i, side])
        ev = prob * price - 1
        if prob < ARGS["min_confidence"] or ev < ARGS["min_edge"] \
           or price < ARGS["min_odds"] or price > ARGS["max_odds"]:
            continue
        if cl[i, side] > 1:
            clvs.append(op[i, side] / cl[i, side] - 1)
    return (float(np.mean(clvs)) if clvs else 0.0, len(clvs))


def main() -> int:
    df = build_features()
    train, val, test = temporal_split(df)
    model = fit_lgbm(train)
    pe_val, pe_test = elo_probabilities(train, val), elo_probabilities(train, test)
    pm_val, pm_test = model.predict_proba(val[FEATURE_COLS]), model.predict_proba(test[FEATURE_COLS])
    w = tune_blend(val["outcome"].to_numpy(), pm_val, pe_val)
    pb_val = w * pm_val + (1 - w) * pe_val
    pb_test = w * pm_test + (1 - w) * pe_test
    calib = TemperatureScaling().fit(pb_val, val["outcome"].to_numpy())
    pbc = calib.transform(pb_test)

    variants = {
        "cloture_moyenne": _priced(test, "close"),
        "ouverture": _priced(test, "open"),
        "meilleure_cloture": _priced(test, "best"),
    }
    report = {}
    print(f"{'Prix':20}{'paris':>8}{'ROI %':>10}{'winrate':>10}{'cote moy':>10}")
    for name, d in variants.items():
        _, stats = simulate(d, pbc, **ARGS)
        report[name] = {k: stats[k] for k in ("n_bets", "roi_pct", "win_rate_pct", "avg_odds")}
        print(f"{name:20}{stats['n_bets']:>8}{stats['roi_pct']:>10.2f}{stats['win_rate_pct']:>10.2f}{stats['avg_odds']:>10.3f}")

    clv, n = _mean_clv(test, pbc)
    report["clv_moyenne_ouverture"] = {"mean_clv_pct": round(100 * clv, 2), "n_bets": n}
    print(f"\nCLV moyenne (paris sélectionnés à l'ouverture) : {100 * clv:+.2f}% sur {n} paris")
    print("  > 0 = edge réel (la clôture bouge en notre faveur) ; < 0 = pas d'edge.")

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nÉcrit {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
