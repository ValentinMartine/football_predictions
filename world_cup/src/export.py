"""
Génère data/predictions.json (artefact web) : métriques Elo vs blend + prédictions
rétrospectives par match du Mondial 2026 (issue + score prédits vs réels).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import log_loss

from src.calibration import TemperatureScaling

from src.pipeline import build_features, FEATURE_COLS
from src.poisson import best_score_for_outcome, elo_lambdas, score_distribution

OUT = Path(__file__).resolve().parents[1] / "data" / "predictions.json"
SHOOTOUTS = Path(__file__).resolve().parents[1] / "data" / "shootouts.csv"
TRAIN_END = pd.Timestamp("2022-01-01")
TEST_START = pd.Timestamp("2023-01-01")
LABELS = ["H", "D", "A"]


def _score_outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def _score_winner(home: str, away: str, home_goals: int, away_goals: int) -> str | None:
    if home_goals > away_goals:
        return home
    if away_goals > home_goals:
        return away
    return None


def _load_shootouts() -> dict[tuple[str, str, str], dict[str, str | None]]:
    if not SHOOTOUTS.exists():
        return {}
    shootouts = pd.read_csv(SHOOTOUTS)
    shootouts = shootouts.dropna(subset=["date", "home_team", "away_team", "winner"])
    out: dict[tuple[str, str, str], dict[str, str | None]] = {}
    for row in shootouts.itertuples(index=False):
        first_shooter = None if pd.isna(row.first_shooter) else str(row.first_shooter)
        out[(str(row.date), str(row.home_team), str(row.away_team))] = {
            "winner": str(row.winner),
            "first_shooter": first_shooter,
        }
    return out


def _shootout_rates(k: float = 6.0) -> dict[str, float]:
    """Taux de victoire historique aux tirs au but par équipe, régularisé vers 50 %
    (prior de force k) car les échantillons sont petits. Sert au départage des KO nuls."""
    if not SHOOTOUTS.exists():
        return {}
    s = pd.read_csv(SHOOTOUTS).dropna(subset=["home_team", "away_team", "winner"])
    played: dict[str, int] = {}
    won: dict[str, int] = {}
    for row in s.itertuples(index=False):
        for team in (str(row.home_team), str(row.away_team)):
            played[team] = played.get(team, 0) + 1
        won[str(row.winner)] = won.get(str(row.winner), 0) + 1
    return {t: (won.get(t, 0) + 0.5 * k) / (n + k) for t, n in played.items()}


def _elo_probs(df, b, mu):
    probs, scores = [], []
    for ed in df["elo_diff"].values:
        lh, la = elo_lambdas(ed, b, mu)
        ph, pdw, pa, best = score_distribution(lh, la)
        probs.append([ph, pdw, pa])
        scores.append(best)
    return np.array(probs), scores


def _acc_ll(y, probs):
    return float((probs.argmax(1) == y).mean()), float(log_loss(y, probs, labels=[0, 1, 2]))


def _outcome_consistent_scores(df, probs, b, mu):
    # Score attendu = buts attendus (Elo->Poisson) arrondis : montre les nuls (1-1) sur matchs serrés.
    scores = []
    for ed in df["elo_diff"].values:
        lh, la = elo_lambdas(ed, b, mu)
        scores.append((int(lh + 0.5), int(la + 0.5)))
    return scores


def main():
    df = build_features()
    shootouts = _load_shootouts()
    shootout_rates = _shootout_rates()
    train = df[df["date"] < TRAIN_END]
    val = df[(df["date"] >= TRAIN_END) & (df["date"] < TEST_START)]
    test = df[df["date"] >= TEST_START]
    wc = df[df["is_wc26"]].copy()

    ed, gd = train["elo_diff"].values, (train["home_score"] - train["away_score"]).values
    b = float((ed * gd).sum() / (ed * ed).sum())
    mu = float((train["home_score"] + train["away_score"]).mean())

    model = LGBMClassifier(n_estimators=400, learning_rate=0.03, max_depth=5, num_leaves=31,
                           subsample=0.8, colsample_bytree=0.8, min_child_samples=50,
                           random_state=42, verbose=-1)
    model.fit(train[FEATURE_COLS], train["outcome"])

    pe_val, _ = _elo_probs(val, b, mu)
    pm_val = model.predict_proba(val[FEATURE_COLS])
    yv = val["outcome"].values
    ws = np.linspace(0, 1, 21)
    w = float(min(ws, key=lambda w: log_loss(yv, w * pm_val + (1 - w) * pe_val, labels=[0, 1, 2])))

    # Calibration température ajustée sur la validation (probabilités affichées honnêtes).
    pb_val = w * pm_val + (1 - w) * pe_val
    calibrator = TemperatureScaling().fit(pb_val, yv)

    def eval_set(d):
        pe, escores = _elo_probs(d, b, mu)
        pm = model.predict_proba(d[FEATURE_COLS])
        pb = w * pm + (1 - w) * pe
        pbc = calibrator.transform(pb)
        display_scores = _outcome_consistent_scores(d, pb, b, mu)
        y = d["outcome"].values
        exact = np.mean([s == (hs, as_) for s, hs, as_ in zip(display_scores, d["home_score"], d["away_score"])])
        elo_acc, elo_ll = _acc_ll(y, pe)
        b_acc, b_ll = _acc_ll(y, pb)
        c_acc, c_ll = _acc_ll(y, pbc)
        return pe, pbc, display_scores, dict(
            elo_accuracy=round(elo_acc, 4), elo_log_loss=round(elo_ll, 4),
            accuracy=round(b_acc, 4), log_loss=round(b_ll, 4),
            calibrated_accuracy=round(c_acc, 4), calibrated_log_loss=round(c_ll, 4),
            exact_score=round(float(exact), 4), n=int(len(d)))

    _, _, _, test_metrics = eval_set(test)
    pe_wc, pb_wc, escores_wc, wc_metrics = eval_set(wc)

    matches = []
    for i, (_, r) in enumerate(wc.iterrows()):
        probs = pb_wc[i]
        pred = int(probs.argmax())
        actual = int(r["outcome"])
        score_home, score_away = escores_wc[i]
        actual_home = int(r["home_score"])
        actual_away = int(r["away_score"])
        shootout = shootouts.get((r["date"].strftime("%Y-%m-%d"), r["home_team"], r["away_team"]))
        actual_score_winner = _score_winner(r["home_team"], r["away_team"], actual_home, actual_away)
        pred_score_winner = _score_winner(r["home_team"], r["away_team"], score_home, score_away)
        # Départage d'un nul en KO : force du match (proba de victoire) + compétence
        # historique aux tirs au but (régularisée), combinées.
        denom = probs[0] + probs[2]
        home_share = float(probs[0] / denom) if denom > 0 else 0.5
        sr_home = shootout_rates.get(r["home_team"], 0.5)
        sr_away = shootout_rates.get(r["away_team"], 0.5)
        TB_LAMBDA = 0.5
        home_tb = home_share + TB_LAMBDA * (sr_home - 0.5)
        away_tb = (1.0 - home_share) + TB_LAMBDA * (sr_away - 0.5)
        pred_tiebreak_winner = r["home_team"] if home_tb >= away_tb else r["away_team"]
        pred_decisive_winner = pred_score_winner or pred_tiebreak_winner
        actual_decisive_winner = actual_score_winner or (shootout["winner"] if shootout else None)
        is_knockout = bool(r.get("is_world_cup_knockout_stage", 0))
        stage = next((s for s in ["group", "round_of_32", "round_of_16", "quarter_final", "semi_final", "third_place", "final"] if r.get(f"stage_{s}", 0)), "group")
        matches.append({
            "date": r["date"].strftime("%Y-%m-%d"),
            "home": r["home_team"], "away": r["away_team"],
            "p_home": round(float(probs[0]), 3), "p_draw": round(float(probs[1]), 3),
            "p_away": round(float(probs[2]), 3),
            "pred_outcome": LABELS[pred],
            "pred_score": f"{score_home}-{score_away}",
            "pred_score_before_shootout": f"{score_home}-{score_away}",
            "pred_score_outcome": _score_outcome(score_home, score_away),
            "pred_decisive_winner": pred_decisive_winner,
            "actual_score": f"{actual_home}-{actual_away}",
            "actual_score_before_shootout": f"{actual_home}-{actual_away}",
            "actual_shootout_winner": shootout["winner"] if shootout else None,
            "actual_shootout_first_shooter": shootout["first_shooter"] if shootout else None,
            "actual_decisive_winner": actual_decisive_winner,
            "actual_outcome": LABELS[actual],
            "correct": pred == actual,
            "decisive_correct": actual_decisive_winner is not None and pred_decisive_winner == actual_decisive_winner,
            "exact": escores_wc[i] == (actual_home, actual_away),
            "is_knockout": is_knockout,
            "stage": stage,
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Elo football + FIFA rankings + recent form + LightGBM (blend tuned on validation), scores via Poisson",
        "score_definition": (
            "results.csv provides the score before penalty shootouts: it can include extra time, "
            "but it does not separate the 90-minute score from the 120-minute score. shootouts.csv "
            "adds the penalty shootout winner and first shooter when available, but not the shootout score."
        ),
        "shootout_count": int(sum(1 for m in matches if m["actual_shootout_winner"])),
        "blend_weight": round(w, 2),
        "calibration_temperature": round(calibrator.T, 3),
        "test_metrics": test_metrics,     # grand test held-out (>=2023)
        "wc_metrics": wc_metrics,         # vitrine Mondial 2026
        "wc_matches": matches,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit : {OUT}")
    print(f"  test large : blend acc={test_metrics['accuracy']} ll={test_metrics['log_loss']} "
          f"(Elo acc={test_metrics['elo_accuracy']} ll={test_metrics['elo_log_loss']})")
    print(f"  WC 2026    : {len(matches)} matchs, blend acc={wc_metrics['accuracy']} "
          f"score exact={wc_metrics['exact_score']}")


if __name__ == "__main__":
    main()
