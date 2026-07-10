"""Compare Dixon-Coles à la baseline Elo (issue, score exact, log-loss)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from src.football_elo import FootballElo
from src.poisson import elo_lambdas, score_distribution
from src.dixon_coles import DixonColes

DATA = Path(__file__).resolve().parents[1] / "data" / "results.csv"
FIT_SINCE = pd.Timestamp("2016-01-01")


def load():
    df = pd.read_csv(DATA).dropna(subset=["home_score", "away_score"]).copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["date"] = pd.to_datetime(df["date"])
    df["neutral"] = df["neutral"].astype(bool)
    return df.sort_values("date").reset_index(drop=True)


def elo_pass(df):
    """elo_diff pré-match pour tous les matchs + calibration b, mu (< 2023)."""
    elo = FootballElo()
    diffs = np.zeros(len(df))
    for k, r in enumerate(df.itertuples(index=False)):
        _, _, ed = elo.pre_match(r.home_team, r.away_team, r.neutral)
        diffs[k] = ed
        elo.update(r.home_team, r.away_team, r.home_score, r.away_score, r.tournament, r.neutral)
    return diffs


def outcome(hs, as_):
    return 0 if hs > as_ else (1 if hs == as_ else 2)


def evaluate(name, df_eval, dc, elo_diffs_eval, b, mu):
    y = np.array([outcome(r.home_score, r.away_score) for r in df_eval.itertuples()])
    # Elo baseline
    pe, escore = [], []
    for ed in elo_diffs_eval:
        lh, la = elo_lambdas(ed, b, mu)
        ph, pdw, pa, best = score_distribution(lh, la)
        pe.append([ph, pdw, pa]); escore.append(best)
    pe = np.array(pe)
    # Dixon-Coles
    pd_, dscore = [], []
    for r in df_eval.itertuples():
        ph, pdw, pa, best = dc.predict(r.home_team, r.away_team, r.neutral)
        pd_.append([ph, pdw, pa]); dscore.append(best)
    pd_ = np.array(pd_)
    actual = [(r.home_score, r.away_score) for r in df_eval.itertuples()]

    def row(label, probs, scores):
        acc = (probs.argmax(1) == y).mean()
        ll = log_loss(y, probs, labels=[0, 1, 2])
        ex = np.mean([s == a for s, a in zip(scores, actual)]) if scores else float("nan")
        print(f"  {label:16}{acc*100:>8.1f}%{ll:>11.4f}{ex*100:>13.1f}%")

    print(f"\n== {name} ({len(df_eval)} matchs) ==")
    print(f"  {'Modèle':16}{'Issue':>9}{'Log-loss':>11}{'Score exact':>13}")
    row("Baseline Elo", pe, escore)
    row("Dixon-Coles", pd_, dscore)


def main():
    df = load()
    diffs = elo_pass(df)
    df = df.assign(elo_diff=diffs)
    pre = df[df["date"] < pd.Timestamp("2023-01-01")]
    b = float((pre["elo_diff"] * (pre["home_score"] - pre["away_score"])).sum() / (pre["elo_diff"] ** 2).sum())
    mu = float((pre["home_score"] + pre["away_score"]).mean())

    # Grand test 2023+ : DC ajusté sur [2016, 2023)
    test = df[df["date"] >= pd.Timestamp("2023-01-01")]
    dc_test = DixonColes().fit(df[(df["date"] >= FIT_SINCE) & (df["date"] < pd.Timestamp("2023-01-01"))],
                               pd.Timestamp("2023-01-01"))
    evaluate("TEST large (>=2023)", test, dc_test, test["elo_diff"].values, b, mu)

    # Vitrine Mondial 2026 : DC ajusté sur [2016, 2026-06-11)
    wc = df[(df["date"] >= pd.Timestamp("2026-06-11")) & (df["tournament"].str.lower() == "fifa world cup")]
    dc_wc = DixonColes().fit(df[(df["date"] >= FIT_SINCE) & (df["date"] < pd.Timestamp("2026-06-11"))],
                             pd.Timestamp("2026-06-11"))
    evaluate("VITRINE Mondial 2026", wc, dc_wc, wc["elo_diff"].values, b, mu)


if __name__ == "__main__":
    main()
