"""Tests unitaires pour la modélisation des buts et Dixon-Coles (src/poisson.py)."""
import numpy as np
import pytest
from src.poisson import (
    dixon_coles_tau,
    fit_elo_goal_model,
    lambdas_from_elo,
    most_likely_score,
    outcome_probs,
    score_matrix,
)


class TestPoissonDixonColes:
    def test_dixon_coles_tau_neutral_for_high_scores(self):
        # Pour tout score supérieur ou égal à 2 buts, tau vaut 1.0
        assert dixon_coles_tau(2, 0, 1.4, 1.1, -0.06) == 1.0
        assert dixon_coles_tau(2, 2, 1.4, 1.1, -0.06) == 1.0
        assert dixon_coles_tau(3, 1, 1.4, 1.1, -0.06) == 1.0

    def test_dixon_coles_tau_adjusts_low_scores(self):
        lam, mu, rho = 1.3, 1.1, -0.06
        # rho < 0 augmente P(0,0) et P(1,1)
        assert dixon_coles_tau(0, 0, lam, mu, rho) > 1.0
        assert dixon_coles_tau(1, 1, lam, mu, rho) > 1.0
        # et réduit P(0,1) et P(1,0)
        assert dixon_coles_tau(0, 1, lam, mu, rho) < 1.0
        assert dixon_coles_tau(1, 0, lam, mu, rho) < 1.0

    def test_score_matrix_sums_to_one(self):
        mat = score_matrix(1.5, 1.2, max_goals=8, rho=-0.06)
        assert round(float(mat.sum()), 6) == 1.0
        assert (mat >= 0.0).all()

    def test_outcome_probs_sum_to_one(self):
        p_home, p_draw, p_away = outcome_probs(1.6, 1.0, rho=-0.06)
        assert round(p_home + p_draw + p_away, 6) == 1.0
        assert p_home > p_away  # 1.6 > 1.0, le favori à domicile a plus de chance de gagner

    def test_dixon_coles_augmente_la_probabilite_de_match_nul(self):
        # Comparaison rho=0 (Poisson indépendant standard) vs rho=-0.06 (Dixon-Coles)
        _, p_draw_indep, _ = outcome_probs(1.3, 1.2, rho=0.0)
        _, p_draw_dc, _ = outcome_probs(1.3, 1.2, rho=-0.06)
        assert p_draw_dc > p_draw_indep

    def test_most_likely_score(self):
        score = most_likely_score(1.5, 1.1, rho=-0.06)
        assert isinstance(score, tuple)
        assert len(score) == 2
        assert score[0] >= 0 and score[1] >= 0

    def test_lambdas_from_elo_bounds(self):
        home, away = lambdas_from_elo(0.0, 0.002, 2.7)
        assert home == away == 1.35
        # Forte supériorité domicile
        home_sup, away_sup = lambdas_from_elo(400.0, 0.002, 2.7)
        assert home_sup > away_sup
        assert away_sup >= 0.15
