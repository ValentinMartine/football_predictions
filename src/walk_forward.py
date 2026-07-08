from __future__ import annotations

import pandas as pd

from src.backtesting import ROBUST_POLICY, select_policy, simulate, threshold_curve
from src.modeling import elo_probabilities, fit_lgbm, metrics, tune_blend
from src.pipeline import FEATURE_COLS

FOLDS = [
    ("2022-23", pd.Timestamp("2021-08-01"), pd.Timestamp("2022-08-01"), pd.Timestamp("2023-08-01")),
    ("2023-24", pd.Timestamp("2022-08-01"), pd.Timestamp("2023-08-01"), pd.Timestamp("2024-08-01")),
    ("2024-25", pd.Timestamp("2023-08-01"), pd.Timestamp("2024-08-01"), pd.Timestamp("2025-08-01")),
    ("2025-26", pd.Timestamp("2024-08-01"), pd.Timestamp("2025-08-01"), pd.Timestamp("2026-08-01")),
]


def _policy_args(policy: dict) -> dict:
    return {
        "min_confidence": policy["threshold"],
        "min_edge": policy["min_edge"],
        "min_odds": policy["min_odds"],
        "max_odds": policy["max_odds"],
    }


def run_walk_forward(df: pd.DataFrame) -> dict:
    selected_rows = []
    fixed_rows = []
    for label, val_start, test_start, test_end in FOLDS:
        train = df[df["date"] < val_start].copy()
        val = df[(df["date"] >= val_start) & (df["date"] < test_start)].copy()
        test = df[(df["date"] >= test_start) & (df["date"] < test_end)].copy()
        if min(len(train), len(val), len(test)) == 0:
            continue

        model = fit_lgbm(train)
        pe_val = elo_probabilities(train, val)
        pe_test = elo_probabilities(train, test)
        pm_val = model.predict_proba(val[FEATURE_COLS])
        pm_test = model.predict_proba(test[FEATURE_COLS])
        weight = tune_blend(val["outcome"].to_numpy(), pm_val, pe_val)
        pb_val = weight * pm_val + (1 - weight) * pe_val
        pb_test = weight * pm_test + (1 - weight) * pe_test
        test_metrics = metrics(test["outcome"].to_numpy(), pb_test)

        curve = threshold_curve(val, pb_val, min_bets=50)
        selected_policy = select_policy(curve, min_bets=100)
        _, selected_stats = simulate(test, pb_test, **_policy_args(selected_policy))
        _, fixed_stats = simulate(test, pb_test, **_policy_args(ROBUST_POLICY))

        selected_rows.append({
            "season": label,
            "blend_weight": round(weight, 2),
            "accuracy": test_metrics["accuracy"],
            "log_loss": test_metrics["log_loss"],
            "policy": {k: selected_policy[k] for k in ("threshold", "min_edge", "min_odds", "max_odds")},
            **selected_stats,
        })
        fixed_rows.append({
            "season": label,
            **fixed_stats,
        })

    return {
        "validation_selected": {
            "folds": selected_rows,
            "aggregate": _aggregate(selected_rows),
        },
        "fixed_robust_policy": {
            "policy": ROBUST_POLICY,
            "folds": fixed_rows,
            "aggregate": _aggregate(fixed_rows),
        },
    }


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {"folds": 0, "n_bets": 0, "roi_pct": 0.0, "total_profit": 0.0}
    total_profit = sum(float(row.get("total_profit", 0.0)) for row in rows)
    total_staked = sum(float(row.get("total_staked", 0.0)) for row in rows)
    return {
        "folds": len(rows),
        "n_bets": int(sum(int(row.get("n_bets", 0)) for row in rows)),
        "roi_pct": round(float(100 * total_profit / total_staked), 2) if total_staked else 0.0,
        "total_profit": round(float(total_profit), 2),
    }
