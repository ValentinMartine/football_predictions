"""
Calibration des probabilités multi-classes (1/N/2).

Une régression isotone one-vs-rest par classe est ajustée sur un jeu de validation
tenu à l'écart de l'entraînement, puis les sorties sont renormalisées pour sommer à 1.
Objectif : que « 60 % » signifie vraiment 60 %, condition nécessaire à un edge de pari
réel (edge = proba × cote − 1 n'a de sens que si la proba est calibrée).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression


class TemperatureScaling:
    """Calibration par mise à l'échelle en température (1 paramètre).

    Divise les log-probabilités par T > 0 avant re-softmax. T > 1 tempère la
    sur-confiance, T < 1 l'accentue. Robuste au surapprentissage (contrairement à
    l'isotone), T est ajusté par minimisation de la log-loss sur la validation.
    """

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


class IsotonicCalibrator:
    def __init__(self) -> None:
        self.models: list[IsotonicRegression] = []

    def fit(self, probs: np.ndarray, y: np.ndarray) -> "IsotonicCalibrator":
        y = np.asarray(y)
        self.models = []
        for k in range(probs.shape[1]):
            ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            ir.fit(probs[:, k], (y == k).astype(float))
            self.models.append(ir)
        return self

    def transform(self, probs: np.ndarray) -> np.ndarray:
        cols = [self.models[k].transform(probs[:, k]) for k in range(probs.shape[1])]
        out = np.clip(np.column_stack(cols), 1e-6, 1.0)
        return out / out.sum(axis=1, keepdims=True)
