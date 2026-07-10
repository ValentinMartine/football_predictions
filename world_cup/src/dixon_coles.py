"""
Modèle Dixon-Coles (Poisson bivarié) pour le football.

Extension du double-Poisson qui corrige la sous-estimation des scores faibles
(0-0, 1-0, 0-1, 1-1) via un paramètre rho, avec pondération temporelle (les matchs
récents comptent plus). Estimation par maximum de vraisemblance (L-BFGS-B).

λ_domicile = exp(attaque_dom - défense_ext + avantage_terrain)
λ_extérieur = exp(attaque_ext - défense_dom)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10


def _tau(i, j, lam, mu, rho):
    """Correction Dixon-Coles des scores faibles."""
    out = np.ones_like(lam)
    out = np.where((i == 0) & (j == 0), 1 - lam * mu * rho, out)
    out = np.where((i == 0) & (j == 1), 1 + lam * rho, out)
    out = np.where((i == 1) & (j == 0), 1 + mu * rho, out)
    out = np.where((i == 1) & (j == 1), 1 - rho, out)
    return out


class DixonColes:
    def __init__(self, xi: float = 0.0018):
        self.xi = xi  # décroissance temporelle (par jour)
        self.teams: list[str] = []
        self.idx: dict[str, int] = {}
        self.attack = self.defense = None
        self.home_adv = 0.3
        self.rho = -0.05

    def fit(self, df: pd.DataFrame, ref_date: pd.Timestamp) -> "DixonColes":
        self.teams = sorted(set(df["home_team"]) | set(df["away_team"]))
        self.idx = {t: k for k, t in enumerate(self.teams)}
        n = len(self.teams)

        h = df["home_team"].map(self.idx).to_numpy()
        a = df["away_team"].map(self.idx).to_numpy()
        hs = df["home_score"].to_numpy()
        as_ = df["away_score"].to_numpy()
        neutral = df["neutral"].to_numpy().astype(bool)
        days = (ref_date - df["date"]).dt.days.to_numpy()
        w = np.exp(-self.xi * np.clip(days, 0, None))

        i0 = (hs == 0).astype(int) + (hs == 1).astype(int) * 1  # pour _tau: valeurs 0/1
        hs01 = np.clip(hs, 0, 1)
        as01 = np.clip(as_, 0, 1)

        def nll(p):
            att = p[:n]
            dfs = p[n:2 * n]
            home, rho = p[2 * n], p[2 * n + 1]
            log_lam = att[h] - dfs[a] + np.where(neutral, 0.0, home)
            log_mu = att[a] - dfs[h]
            lam = np.exp(log_lam)
            mu = np.exp(log_mu)
            tau = _tau(hs01, as01, lam, mu, rho)
            tau = np.clip(tau, 1e-6, None)
            ll = np.log(tau) + hs * log_lam - lam + as_ * log_mu - mu
            return -np.sum(w * ll) + 1e-3 * (att @ att + dfs @ dfs)

        p0 = np.concatenate([np.zeros(n), np.zeros(n), [0.3], [-0.05]])
        res = minimize(nll, p0, method="L-BFGS-B",
                       bounds=[(-3, 3)] * (2 * n) + [(-1, 1), (-0.2, 0.2)],
                       options={"maxiter": 200})
        self.attack = res.x[:n]
        self.defense = res.x[n:2 * n]
        self.home_adv = float(res.x[2 * n])
        self.rho = float(res.x[2 * n + 1])
        return self

    def _lambdas(self, home: str, away: str, neutral: bool) -> tuple[float, float]:
        ih, ia = self.idx.get(home), self.idx.get(away)
        if ih is None or ia is None:
            return 1.3, 1.1
        adv = 0.0 if neutral else self.home_adv
        lam = math_exp(self.attack[ih] - self.defense[ia] + adv)
        mu = math_exp(self.attack[ia] - self.defense[ih])
        return lam, mu

    def predict(self, home: str, away: str, neutral: bool):
        """Retourne (p_home, p_draw, p_away, (score_home, score_away) le plus probable)."""
        lam, mu = self._lambdas(home, away, neutral)
        ph = poisson.pmf(np.arange(MAX_GOALS + 1), lam)
        pa = poisson.pmf(np.arange(MAX_GOALS + 1), mu)
        mat = np.outer(ph, pa)
        # correction DC sur le coin bas-gauche
        for i in (0, 1):
            for j in (0, 1):
                mat[i, j] *= _tau(np.array(i), np.array(j), np.array(lam), np.array(mu), self.rho)
        mat = np.clip(mat, 0.0, None)
        mat /= mat.sum()
        p_home = max(np.tril(mat, -1).sum(), 1e-9)
        p_draw = max(np.trace(mat), 1e-9)
        p_away = max(np.triu(mat, 1).sum(), 1e-9)
        s = p_home + p_draw + p_away
        p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s
        bi, bj = np.unravel_index(mat.argmax(), mat.shape)
        return float(p_home), float(p_draw), float(p_away), (int(bi), int(bj))


def math_exp(x: float) -> float:
    return float(np.exp(x))
