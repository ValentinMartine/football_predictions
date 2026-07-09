from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtesting import ROBUST_POLICY, select_policy, simulate, threshold_curve
from src.calibration import TemperatureScaling
from src.lineups import lineup_adjusted_prediction
from src.modeling import elo_probabilities, fit_lgbm, metrics, temporal_split, tune_blend
from src.pipeline import FEATURE_COLS, build_features
from src.walk_forward import run_walk_forward

OUT = Path(__file__).resolve().parents[1] / "data" / "predictions.json"
LABELS = ["H", "D", "A"]
LABEL_NAMES = ["home", "draw", "away"]


def _poisson_reg() -> LGBMRegressor:
    return LGBMRegressor(objective="poisson", n_estimators=400, learning_rate=0.03,
                         max_depth=5, num_leaves=31, subsample=0.85, colsample_bytree=0.85,
                         min_child_samples=35, random_state=42, verbose=-1)


def _likely_score(lam_h: float, lam_a: float, outcome: int | None = None) -> str:
    """Score attendu = buts attendus (Poisson) arrondis. Montre naturellement les scores nuls
    (1-1, 0-0) quand les deux équipes sont proches et peu prolifiques, sans forcer la cohérence
    avec l'issue argmax (le nul est rarement l'issue la plus probable, ce qui est normal)."""
    return f"{int(lam_h + 0.5)}-{int(lam_a + 0.5)}"


def _season_label(d) -> str:
    """Libellé de saison football (aoû→mai) à partir d'une date."""
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{start + 1}"


def _prediction_payload(row, probs, stage: str) -> dict:
    if stage == "lineups":
        probs, lineup_features = lineup_adjusted_prediction(probs, None)
    else:
        lineup_features = None
    pred = int(probs.argmax())
    confidence = float(probs[pred])
    return {
        "stage": stage,
        "available": stage == "initial",
        "home": row.home_team,
        "away": row.away_team,
        "p_home": round(float(probs[0]), 3),
        "p_draw": round(float(probs[1]), 3),
        "p_away": round(float(probs[2]), 3),
        "pred_outcome": LABELS[pred],
        "pred_side": LABEL_NAMES[pred],
        "confidence": round(confidence, 3),
        "lineup_features": lineup_features,
    }


BIG5 = {"E0", "SP1", "I1", "D1", "F1"}  # la page 1X2 est brandée "5 grands championnats"


def main() -> None:
    # L'Elo/forme sont calculés sur toutes les ligues téléchargées, mais le modèle 1X2 et
    # les métriques affichées restent sur les 5 grands championnats (cohérence de la page).
    df = build_features()
    df = df[df["league"].isin(BIG5)].reset_index(drop=True)
    train, val, test = temporal_split(df)
    model = fit_lgbm(train)

    pe_val = elo_probabilities(train, val)
    pe_test = elo_probabilities(train, test)
    pm_val = model.predict_proba(val[FEATURE_COLS])
    pm_test = model.predict_proba(test[FEATURE_COLS])
    weight = tune_blend(val["outcome"].to_numpy(), pm_val, pe_val)
    pb_val = weight * pm_val + (1 - weight) * pe_val
    pb_test = weight * pm_test + (1 - weight) * pe_test

    # Calibration isotone ajustée sur la validation (probas honnêtes -> edge de pari réel).
    calibrator = TemperatureScaling().fit(pb_val, val["outcome"].to_numpy())
    pbc_val = calibrator.transform(pb_val)
    pbc_test = calibrator.transform(pb_test)

    # Politique de pari : fixe robuste + politique choisie sur la validation (probas calibrées).
    val_curve = threshold_curve(val, pbc_val, min_bets=50)
    selected = select_policy(val_curve, min_bets=100)
    policy = ROBUST_POLICY.copy()
    policy_args = {
        "min_confidence": policy["threshold"],
        "min_edge": policy["min_edge"],
        "min_odds": policy["min_odds"],
        "max_odds": policy["max_odds"],
    }
    selected_args = {
        "min_confidence": selected["threshold"],
        "min_edge": selected["min_edge"],
        "min_odds": selected["min_odds"],
        "max_odds": selected["max_odds"],
    }
    _, val_backtest = simulate(val, pbc_val, **policy_args)
    bets, test_backtest = simulate(test, pbc_test, **policy_args)
    _, test_backtest_selected = simulate(test, pbc_test, **selected_args)

    # Line shopping : parier à la meilleure cote de clôture disponible (colonnes best_*).
    test_best = test.copy()
    for side in ("home", "draw", "away"):
        test_best[f"odds_{side}"] = pd.to_numeric(test_best[f"best_{side}"], errors="coerce")
    _, test_backtest_best = simulate(test_best, pbc_test, **policy_args)

    # Tous les matchs des deux dernières saisons (filtrables par saison côté site)
    recent = test[test["date"] >= pd.Timestamp("2024-08-01")].copy()
    pe_recent = elo_probabilities(train, recent)
    pm_recent = model.predict_proba(recent[FEATURE_COLS])
    pb_recent = weight * pm_recent + (1 - weight) * pe_recent
    pbc_recent = calibrator.transform(pb_recent)

    # Modèle de score (Poisson) pour un score prédit par match
    reg_h = _poisson_reg().fit(train[FEATURE_COLS], train["home_goals"])
    reg_a = _poisson_reg().fit(train[FEATURE_COLS], train["away_goals"])
    lam_h = np.clip(reg_h.predict(recent[FEATURE_COLS]), 0.05, 7)
    lam_a = np.clip(reg_a.predict(recent[FEATURE_COLS]), 0.05, 7)

    matches = []
    for i, row in enumerate(recent.itertuples(index=False)):
        probs = pbc_recent[i]
        pred = int(probs.argmax())
        matches.append({
            "date": row.date.strftime("%Y-%m-%d"),
            "season": _season_label(row.date),
            "league": row.league_name,
            "home": row.home_team,
            "away": row.away_team,
            "p_home": round(float(probs[0]), 3),
            "p_draw": round(float(probs[1]), 3),
            "p_away": round(float(probs[2]), 3),
            "pred_outcome": LABELS[pred],
            "pred_score": _likely_score(float(lam_h[i]), float(lam_a[i]), pred),
            "actual_outcome": LABELS[int(row.outcome)],
            "actual_score": f"{int(row.home_goals)}-{int(row.away_goals)}",
            "correct": pred == int(row.outcome),
            "prediction_initiale": _prediction_payload(row, probs, "initial"),
            "prediction_apres_compositions": _prediction_payload(row, probs, "lineups"),
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Club Elo + rolling form/shots + LightGBM, blend tuned on temporal validation",
        "data_source": "football-data.co.uk CSV, Big Five leagues, seasons 2015-2016 to 2025-2026",
        "n_matches": int(len(df)),
        "blend_weight": round(weight, 2),
        "calibration_temperature": round(calibrator.T, 3),
        "selected_threshold": policy["threshold"],
        "betting_policy": {
            "selection_source": policy.get("source", "fixed"),
            "min_confidence": policy["threshold"],
            "min_expected_value": policy["min_edge"],
            "min_odds": policy["min_odds"],
            "max_odds": policy["max_odds"],
            "staking": "quarter Kelly capped at 2% bankroll",
            "edge_formula": "expected_value = model_probability * decimal_odds - 1",
            "line_shopping": "Toujours parier à la meilleure cote disponible (colonnes best_*) : gain de prix mécanique et fiable, à la différence du ROI qui reste bruité.",
        },
        "prediction_schema": {
            "prediction_initiale": "Long-term pre-match model: Elo, market odds, rolling form, rest, shots and league context.",
            "prediction_apres_compositions": "Reserved for late pre-match updates from official lineups, absences, formations and minute load.",
        },
        "validation_metrics": {
            "elo": metrics(val["outcome"].to_numpy(), pe_val),
            "ml": metrics(val["outcome"].to_numpy(), pm_val),
            "blend": metrics(val["outcome"].to_numpy(), pb_val),
            "blend_calibrated": metrics(val["outcome"].to_numpy(), pbc_val),
        },
        "test_metrics": {
            "elo": metrics(test["outcome"].to_numpy(), pe_test),
            "ml": metrics(test["outcome"].to_numpy(), pm_test),
            "blend": metrics(test["outcome"].to_numpy(), pb_test),
            "blend_calibrated": metrics(test["outcome"].to_numpy(), pbc_test),
        },
        "backtest": {
            "validation": val_backtest,
            "test": test_backtest,
            "test_line_shopping": test_backtest_best,
            "test_selected_policy": test_backtest_selected,
            "selected_policy": {k: selected[k] for k in ("threshold", "min_edge", "min_odds", "max_odds")},
            "threshold_curve_validation": sorted(val_curve, key=lambda r: r["final_bankroll"], reverse=True)[:30],
        },
        "walk_forward": run_walk_forward(df),
        "recent_matches": matches,
        "recent_bets": [] if bets.empty else bets.tail(20).assign(date=lambda x: x["date"].dt.strftime("%Y-%m-%d")).to_dict("records"),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Ecrit {OUT}")
    print(payload["test_metrics"])
    print(payload["backtest"]["test"])


if __name__ == "__main__":
    main()
