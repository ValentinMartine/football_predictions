from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.backtesting import ROBUST_POLICY, simulate, threshold_curve
from src.modeling import elo_probabilities, fit_lgbm, metrics, temporal_split, tune_blend
from src.pipeline import build_features, FEATURE_COLS


def main() -> None:
    df = build_features()
    train, val, test = temporal_split(df)
    print(f"Dataset {len(df)} matchs | Train {len(train)} | Val {len(val)} | Test {len(test)}")
    print(f"Cotes test: {int(test[['odds_home','odds_draw','odds_away']].notna().all(axis=1).sum())}/{len(test)}")

    model = fit_lgbm(train)
    pe_val = elo_probabilities(train, val)
    pe_test = elo_probabilities(train, test)
    pm_val = model.predict_proba(val[FEATURE_COLS])
    pm_test = model.predict_proba(test[FEATURE_COLS])

    weight = tune_blend(val["outcome"].to_numpy(), pm_val, pe_val)
    pb_val = weight * pm_val + (1 - weight) * pe_val
    pb_test = weight * pm_test + (1 - weight) * pe_test

    yv = val["outcome"].to_numpy()
    yt = test["outcome"].to_numpy()
    print("\nValidation")
    print("Elo      ", metrics(yv, pe_val))
    print("LightGBM ", metrics(yv, pm_val))
    print(f"Blend w={weight:.2f}", metrics(yv, pb_val))
    print("\nTest")
    print("Elo      ", metrics(yt, pe_test))
    print("LightGBM ", metrics(yt, pm_test))
    print(f"Blend w={weight:.2f}", metrics(yt, pb_test))

    print("\nBacktest politiques sur validation")
    val_curve = threshold_curve(val, pb_val, min_bets=50)
    for row in sorted(val_curve, key=lambda r: r["final_bankroll"], reverse=True)[:12]:
        print(row)
    policy = ROBUST_POLICY.copy()
    print(f"\nPolitique fixe walk-forward: {policy}")

    _, val_stats = simulate(
        val,
        pb_val,
        min_confidence=policy["threshold"],
        min_edge=policy["min_edge"],
        min_odds=policy["min_odds"],
        max_odds=policy["max_odds"],
    )
    bets_test, test_stats = simulate(
        test,
        pb_test,
        min_confidence=policy["threshold"],
        min_edge=policy["min_edge"],
        min_odds=policy["min_odds"],
        max_odds=policy["max_odds"],
    )
    print("Backtest validation", val_stats)
    print("Backtest test      ", test_stats)
    if not bets_test.empty:
        print(bets_test.tail(5)[["date", "league", "home_team", "away_team", "prob", "odds", "profit", "bankroll"]].to_string(index=False))


if __name__ == "__main__":
    main()
