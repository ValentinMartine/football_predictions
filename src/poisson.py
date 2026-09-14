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


def dixon_coles_tau(i: int, j: int, lam: float, mu: float, rho: float) -> float:
    """Facteur de correction bivariée de Dixon & Coles (1997) pour corriger la corrélation des scores faibles."""
    if i == 0 and j == 0:
        return max(0.0, 1.0 - lam * mu * rho)
    elif i == 0 and j == 1:
        return max(0.0, 1.0 + lam * rho)
    elif i == 1 and j == 0:
        return max(0.0, 1.0 + mu * rho)
    elif i == 1 and j == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


def score_matrix(home_lambda: float, away_lambda: float, max_goals: int = 8, rho: float = -0.06) -> np.ndarray:
    """Calcule la matrice des probabilités jointes P(X=i, Y=j) avec ajustement Dixon-Coles."""
    home_probs = [math.exp(-home_lambda) * home_lambda ** i / math.factorial(i) for i in range(max_goals + 1)]
    away_probs = [math.exp(-away_lambda) * away_lambda ** j / math.factorial(j) for j in range(max_goals + 1)]
    mat = np.zeros((max_goals + 1, max_goals + 1), dtype=float)
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            tau = dixon_coles_tau(i, j, home_lambda, away_lambda, rho) if rho != 0.0 else 1.0
            mat[i, j] = max(0.0, home_probs[i] * away_probs[j] * tau)
    total = mat.sum()
    if total > 0:
        mat /= total
    return mat


def most_likely_score(home_lambda: float, away_lambda: float, max_goals: int = 8, rho: float = -0.06) -> tuple[int, int]:
    """Retourne le score exact (home, away) le plus probable selon la distribution Dixon-Coles."""
    mat = score_matrix(home_lambda, away_lambda, max_goals=max_goals, rho=rho)
    idx = int(np.argmax(mat))
    i, j = divmod(idx, max_goals + 1)
    return int(i), int(j)


def outcome_probs(home_lambda: float, away_lambda: float, max_goals: int = 8, rho: float = -0.06) -> tuple[float, float, float]:
    """Probabilités (domicile, nul, extérieur) issues du modèle Dixon-Coles (ou Poisson indépendant si rho=0)."""
    mat = score_matrix(home_lambda, away_lambda, max_goals=max_goals, rho=rho)
    p_home = float(np.tril(mat, -1).sum())
    p_draw = float(np.diag(mat).sum())
    p_away = float(np.triu(mat, 1).sum())
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total

