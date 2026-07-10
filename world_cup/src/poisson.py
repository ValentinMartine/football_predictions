"""Distribution de scores Poisson et conversion Elo -> probabilités 1/N/2 + score exact."""
from __future__ import annotations

import math

MAX_GOALS = 10


def _pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_distribution(lam_home: float, lam_away: float):
    """Retourne (p_home, p_draw, p_away, (score_home, score_away) le plus probable)."""
    ph = [_pmf(lam_home, i) for i in range(MAX_GOALS + 1)]
    pa = [_pmf(lam_away, j) for j in range(MAX_GOALS + 1)]
    p_home = p_draw = p_away = 0.0
    best_p, best_score = -1.0, (0, 0)
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = ph[i] * pa[j]
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
            if p > best_p:
                best_p, best_score = p, (i, j)
    s = p_home + p_draw + p_away
    return p_home / s, p_draw / s, p_away / s, best_score


def best_score_for_outcome(lam_home: float, lam_away: float, outcome: int) -> tuple[int, int]:
    """Most likely score constrained to the predicted outcome.

    outcome: 0 = home win, 1 = draw, 2 = away win.
    """
    best_p, best_score = -1.0, (0, 0)
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            if outcome == 0 and i <= j:
                continue
            if outcome == 1 and i != j:
                continue
            if outcome == 2 and i >= j:
                continue
            p = _pmf(lam_home, i) * _pmf(lam_away, j)
            if p > best_p:
                best_p, best_score = p, (i, j)
    return best_score


def elo_lambdas(elo_diff: float, b: float, mu: float) -> tuple[float, float]:
    """Elo -> buts attendus (lam_home, lam_away) via supériorité = b*elo_diff."""
    supremacy = b * elo_diff
    return max(0.15, (mu + supremacy) / 2), max(0.15, (mu - supremacy) / 2)
