"""
Entraîne un modèle ML (LightGBM 3 classes) et le compare à la baseline Elo sur le
Mondial 2026, avec un blend ML+Elo (poids réglé sur une validation temporelle).

Métriques : issue correcte (1/N/2), score exact, log-loss.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import log_loss

from src.pipeline import build_features, FEATURE_COLS
from src.poisson import best_score_for_outcome, elo_lambdas, score_distribution

WC_START = pd.Timestamp("2026-06-11")
TRAIN_END = pd.Timestamp("2022-01-01")   # train : < 2022
TEST_START = pd.Timestamp("2023-01-01")  # test large held-out : >= 2023 (val = 2022)


def elo_probs(df: pd.DataFrame, b: float, mu: float) -> np.ndarray:
    out = np.zeros((len(df), 3))
    scores = []
    for i, ed in enumerate(df["elo_diff"].values):
        lh, la = elo_lambdas(ed, b, mu)
        ph, pd_, pa, best = score_distribution(lh, la)
        out[i] = [ph, pd_, pa]
        scores.append(best)
    return out, scores


def metrics(name, y, probs, exact=None, actual_scores=None):
    pred = probs.argmax(1)
    acc = (pred == y).mean()
    ll = log_loss(y, probs, labels=[0, 1, 2])
    line = f"{name:20}{acc*100:>10.1f}%{ll:>12.4f}"
    if exact is not None:
        ex = np.mean([e == s for e, s in zip(exact, actual_scores)])
        line += f"{ex*100:>14.1f}%"
    else:
        line += f"{'—':>14}"
    print(line)
    return acc, ll


def outcome_consistent_scores(df: pd.DataFrame, probs: np.ndarray, b: float, mu: float) -> list[tuple[int, int]]:
    scores = []
    for ed, outcome in zip(df["elo_diff"].values, probs.argmax(1)):
        lh, la = elo_lambdas(ed, b, mu)
        scores.append(best_score_for_outcome(lh, la, int(outcome)))
    return scores


def main():
    df = build_features()
    train = df[df["date"] < TRAIN_END]
    val = df[(df["date"] >= TRAIN_END) & (df["date"] < TEST_START)]
    test = df[df["date"] >= TEST_START].copy()          # grand test tenu à l'écart
    wc = df[df["is_wc26"]].copy()                         # vitrine Mondial 2026
    print(f"Train {len(train)} | Val {len(val)} | Test (>=2023) {len(test)} | WC26 {len(wc)}")

    # Calibration Elo->buts sur le train
    ed = train["elo_diff"].values
    gd = (train["home_score"] - train["away_score"]).values
    b = float((ed * gd).sum() / (ed * ed).sum())
    mu = float((train["home_score"] + train["away_score"]).mean())

    # Modèle ML (3 classes)
    model = LGBMClassifier(n_estimators=400, learning_rate=0.03, max_depth=5,
                           num_leaves=31, subsample=0.8, colsample_bytree=0.8,
                           min_child_samples=50, random_state=42, verbose=-1)
    model.fit(train[FEATURE_COLS], train["outcome"])

    # Probas Elo / ML
    pe_val, _ = elo_probs(val, b, mu)
    pm_val = model.predict_proba(val[FEATURE_COLS])

    # Poids de blend réglé sur la val (min log-loss)
    yv = val["outcome"].values
    ws = np.linspace(0, 1, 21)
    w = float(min(ws, key=lambda w: log_loss(yv, w * pm_val + (1 - w) * pe_val, labels=[0, 1, 2])))
    print(f"Calibration: b={b:.4f}, mu={mu:.2f} | poids blend ML w*={w:.2f}")

    for label, d in [("TEST large (>=2023)", test), ("VITRINE Mondial 2026", wc)]:
        pe, elo_scores = elo_probs(d, b, mu)
        pm = model.predict_proba(d[FEATURE_COLS])
        pb = w * pm + (1 - w) * pe
        blend_scores = outcome_consistent_scores(d, pb, b, mu)
        y = d["outcome"].values
        actual = list(zip(d["home_score"], d["away_score"]))
        print(f"\n== {label} ({len(d)} matchs) ==")
        print(f"{'Modèle':20}{'Issue':>11}{'Log-loss':>12}{'Score exact':>14}")
        metrics("Baseline Elo", y, pe, elo_scores, actual)
        metrics("ML (LightGBM)", y, pm)
        metrics("Blend ML+Elo", y, pb, blend_scores, actual)


if __name__ == "__main__":
    main()
