"""
Prédiction rétrospective du Mondial 2026.

Pour chaque match déjà joué de la Coupe du monde 2026, on prédit l'issue et le score
en n'utilisant QUE les données antérieures (Elo calculé chronologiquement) :

- Baseline Elo : issue = équipe la mieux notée (nul si écart Elo faible).
- Modèle Poisson : Elo -> supériorité attendue -> buts attendus -> distribution des
  scores -> probas 1/N/2 + score exact le plus probable.

On rapporte le % de bonnes prédictions d'issue et le % de scores exacts, pour montrer
que le modèle dépasse la baseline Elo.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.football_elo import FootballElo, HOME_ADVANTAGE

DATA = Path(__file__).resolve().parents[1] / "data" / "results.csv"
WC_START = "2026-06-11"
MAX_GOALS = 10


def _poisson_pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_distribution(lam_home: float, lam_away: float):
    ph = [_poisson_pmf(lam_home, i) for i in range(MAX_GOALS + 1)]
    pa = [_poisson_pmf(lam_away, j) for j in range(MAX_GOALS + 1)]
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
    return p_home, p_draw, p_away, best_score


def outcome(hs: int, as_: int) -> str:
    return "H" if hs > as_ else ("A" if hs < as_ else "D")


def main() -> None:
    rows = list(csv.DictReader(open(DATA, encoding="utf-8")))
    rows.sort(key=lambda r: r["date"])

    elo = FootballElo()
    sum_xy = sum_xx = 0.0          # calibration supériorité ~ b * elo_diff
    total_goals = n_pre = 0
    abs_diffs: list[float] = []    # pour le seuil de nul de la baseline

    wc_preds = []  # (elo_diff, hs, as, tournament)

    for r in rows:
        hs, as_ = r["home_score"], r["away_score"]
        if not hs.lstrip("-").isdigit() or not as_.lstrip("-").isdigit():
            continue
        hs, as_ = int(hs), int(as_)
        neutral = r["neutral"].lower() == "true"
        eh, ea, ediff = elo.pre_match(r["home_team"], r["away_team"], neutral)

        is_wc = r["date"] >= WC_START and r["tournament"].lower() == "fifa world cup"
        if is_wc:
            wc_preds.append((ediff, hs, as_, r["home_team"], r["away_team"], r["date"]))
        elif r["date"] < WC_START:
            sum_xy += ediff * (hs - as_)
            sum_xx += ediff * ediff
            total_goals += hs + as_
            n_pre += 1
            abs_diffs.append(abs(ediff))

        elo.update(r["home_team"], r["away_team"], hs, as_, r["tournament"], neutral)

    b = sum_xy / sum_xx if sum_xx else 0.0          # buts d'écart par point d'Elo
    mu = total_goals / n_pre if n_pre else 2.6      # total de buts moyen
    abs_diffs.sort()
    # seuil de nul baseline : cale la fréquence de nul historique (~ 23 %)
    draw_threshold = abs_diffs[int(len(abs_diffs) * 0.23)]

    print(f"Calibration (sur {n_pre} matchs pré-Mondial) : "
          f"buts/point Elo = {b:.4f}, total buts moyen = {mu:.2f}, seuil nul Elo = {draw_threshold:.0f}")
    print(f"Matchs Coupe du monde 2026 évalués : {len(wc_preds)}\n")

    elo_ok = pois_ok = exact_ok = 0
    ll_model = ll_base = 0.0
    base_rates = {"H": 0.49, "D": 0.23, "A": 0.28}  # base historique approx

    for ediff, hs, as_, home, away, date in wc_preds:
        actual = outcome(hs, as_)

        # Baseline Elo
        if abs(ediff) < draw_threshold:
            elo_pred = "D"
        else:
            elo_pred = "H" if ediff > 0 else "A"
        elo_ok += elo_pred == actual

        # Modèle Poisson
        supremacy = b * ediff
        lam_h = max(0.15, (mu + supremacy) / 2)
        lam_a = max(0.15, (mu - supremacy) / 2)
        p_h, p_d, p_a, best_score = score_distribution(lam_h, lam_a)
        s = p_h + p_d + p_a
        p_h, p_d, p_a = p_h / s, p_d / s, p_a / s
        probs = {"H": p_h, "D": p_d, "A": p_a}
        model_pred = max(probs, key=probs.get)
        pois_ok += model_pred == actual
        exact_ok += best_score == (hs, as_)

        ll_model += -math.log(max(probs[actual], 1e-9))
        ll_base += -math.log(base_rates[actual])

    n = len(wc_preds)
    print(f"{'Métrique':32}{'Baseline Elo':>14}{'Modèle Poisson':>16}")
    print(f"{'Issue correcte (1/N/2)':32}{elo_ok/n*100:>13.1f}%{pois_ok/n*100:>15.1f}%")
    print(f"{'Score exact':32}{'—':>14}{exact_ok/n*100:>15.1f}%")
    print(f"{'Log-loss (issue)':32}{ll_base/n:>14.4f}{ll_model/n:>16.4f}")
    print(f"\n(log-loss base = taux de base historiques ; plus bas = mieux)")


if __name__ == "__main__":
    main()
