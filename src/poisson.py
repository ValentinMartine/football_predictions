from __future__ import annotations

import math

import numpy as np


def fit_elo_goal_model(elo_diff: np.ndarray, goal_diff: np.ndarray, total_goals: np.ndarray) -> tuple[float, float]:
    denom = float((elo_diff * elo_diff).sum())
    slope = float((elo_diff * goal_diff).sum() / denom) if denom else 0.0
    mean_goals = float(np.nanmean(total_goals))
    return slope, mean_goals


def lambdas_from_elo(elo_diff: float, slope: float, mean_goals: float) -> tuple[float, float]:
    expected_diff = float(np.clip(slope * elo_diff, -2.8, 2.8))
    home = max(0.15, mean_goals / 2 + expected_diff / 2)
    away = max(0.15, mean_goals / 2 - expected_diff / 2)
    return home, away


def outcome_probs(home_lambda: float, away_lambda: float, max_goals: int = 8) -> tuple[float, float, float]:
    home_probs = [math.exp(-home_lambda) * home_lambda ** i / math.factorial(i) for i in range(max_goals + 1)]
    away_probs = [math.exp(-away_lambda) * away_lambda ** i / math.factorial(i) for i in range(max_goals + 1)]
    p_home = p_draw = p_away = 0.0
    for i, ph in enumerate(home_probs):
        for j, pa in enumerate(away_probs):
            p = ph * pa
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total
