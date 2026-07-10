"""Measure the contribution of FIFA ranking features.

The comparison keeps the same temporal split and Elo/ML blend as the main
export, then trains three feature sets:
- all features;
- all features except FIFA ranking variables;
- FIFA ranking variables plus basic match context.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import log_loss

from src.export import TEST_START, TRAIN_END, _acc_ll, _elo_probs
from src.pipeline import FEATURE_COLS, build_features

FIFA_FEATURES = {c for c in FEATURE_COLS if c.startswith("fifa_") or c == "has_fifa_rank"}
CONTEXT_FEATURES = {
    "neutral",
    "tourn_k",
    "is_friendly",
    "is_world_cup",
    "is_qualifier",
    "is_continental",
    "is_nations_league",
}


def _fit_blend(train, val, eval_set, cols, b: float, mu: float) -> tuple[float, float, float]:
    model = LGBMClassifier(
        n_estimators=400,
        learning_rate=0.03,
        max_depth=5,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=50,
        random_state=42,
        verbose=-1,
    )
    model.fit(train[cols], train["outcome"])

    pe_val, _ = _elo_probs(val, b, mu)
    pm_val = model.predict_proba(val[cols])
    y_val = val["outcome"].values
    weights = np.linspace(0, 1, 21)
    w = float(min(weights, key=lambda x: log_loss(y_val, x * pm_val + (1 - x) * pe_val, labels=[0, 1, 2])))

    pe_eval, _ = _elo_probs(eval_set, b, mu)
    pm_eval = model.predict_proba(eval_set[cols])
    probs = w * pm_eval + (1 - w) * pe_eval
    acc, ll = _acc_ll(eval_set["outcome"].values, probs)
    return w, acc, ll


def main() -> None:
    df = build_features()
    train = df[df["date"] < TRAIN_END]
    val = df[(df["date"] >= TRAIN_END) & (df["date"] < TEST_START)]
    test = df[df["date"] >= TEST_START]
    wc = df[df["is_wc26"]].copy()

    elo_diff = train["elo_diff"].values
    goal_diff = (train["home_score"] - train["away_score"]).values
    b = float((elo_diff * goal_diff).sum() / (elo_diff * elo_diff).sum())
    mu = float((train["home_score"] + train["away_score"]).mean())

    feature_sets = {
        "all_features": FEATURE_COLS,
        "without_fifa": [c for c in FEATURE_COLS if c not in FIFA_FEATURES],
        "fifa_only_plus_context": [c for c in FEATURE_COLS if c in FIFA_FEATURES or c in CONTEXT_FEATURES],
    }

    print(f"train={len(train)} val={len(val)} test={len(test)} wc={len(wc)}")
    print(f"{'feature_set':24} {'w':>4} {'test_acc':>9} {'test_ll':>9} {'wc_acc':>9} {'wc_ll':>9}")
    for name, cols in feature_sets.items():
        w_test, test_acc, test_ll = _fit_blend(train, val, test, cols, b, mu)
        _, wc_acc, wc_ll = _fit_blend(train, val, wc, cols, b, mu)
        print(f"{name:24} {w_test:4.2f} {test_acc:9.4f} {test_ll:9.4f} {wc_acc:9.4f} {wc_ll:9.4f}")


if __name__ == "__main__":
    main()
