"""Calibration par mise à l'échelle en température (1 paramètre) pour les probabilités
1/N/2. Divise les log-probabilités par T > 0 avant re-softmax ; T ajusté par minimisation
de la log-loss sur la validation. Robuste au surapprentissage (contrairement à l'isotone)."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar


class TemperatureScaling:
    def __init__(self) -> None:
        self.T = 1.0

    def _apply(self, probs: np.ndarray, T: float) -> np.ndarray:
        z = np.log(np.clip(probs, 1e-12, 1.0)) / T
        z = z - z.max(axis=1, keepdims=True)
        p = np.exp(z)
        return p / p.sum(axis=1, keepdims=True)

    def fit(self, probs: np.ndarray, y: np.ndarray) -> "TemperatureScaling":
        y = np.asarray(y)
        rows = np.arange(len(y))

        def nll(T: float) -> float:
            p = self._apply(probs, T)
            return float(-np.mean(np.log(np.clip(p[rows, y], 1e-12, 1.0))))

        res = minimize_scalar(nll, bounds=(0.5, 3.0), method="bounded")
        self.T = float(res.x)
        return self

    def transform(self, probs: np.ndarray) -> np.ndarray:
        return self._apply(probs, self.T)
