from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, log_loss

from src.pipeline import FEATURE_COLS
from src.poisson import fit_elo_goal_model, lambdas_from_elo, outcome_probs


def temporal_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = df[df["date"] < pd.Timestamp("2023-08-01")].copy()
    val = df[(df["date"] >= pd.Timestamp("2023-08-01")) & (df["date"] < pd.Timestamp("2024-08-01"))].copy()
    test = df[df["date"] >= pd.Timestamp("2024-08-01")].copy()
    return train, val, test


def fit_lgbm(train: pd.DataFrame) -> LGBMClassifier:
    model = LGBMClassifier(
        objective="multiclass",
        num_class=3,
        n_estimators=500,
        learning_rate=0.025,
        max_depth=5,
        num_leaves=31,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_samples=35,
        random_state=42,
        verbose=-1,
    )
    model.fit(train[FEATURE_COLS], train["outcome"])
    return model


def elo_probabilities(train: pd.DataFrame, df: pd.DataFrame) -> np.ndarray:
    slope, mean_goals = fit_elo_goal_model(
        train["elo_diff"].to_numpy(),
        (train["home_goals"] - train["away_goals"]).to_numpy(),
        (train["home_goals"] + train["away_goals"]).to_numpy(),
    )
    return np.array([outcome_probs(*lambdas_from_elo(v, slope, mean_goals)) for v in df["elo_diff"]])


def tune_blend(y: np.ndarray, ml_probs: np.ndarray, elo_probs: np.ndarray) -> float:
    weights = np.linspace(0, 1, 41)
    return float(min(weights, key=lambda w: log_loss(y, w * ml_probs + (1 - w) * elo_probs, labels=[0, 1, 2])))


def metrics(y: np.ndarray, probs: np.ndarray) -> dict:
    return {
        "accuracy": round(float(accuracy_score(y, probs.argmax(axis=1))), 4),
        "log_loss": round(float(log_loss(y, probs, labels=[0, 1, 2])), 4),
    }
