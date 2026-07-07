from __future__ import annotations

import numpy as np
import pandas as pd

ODDS_COLS = ["odds_home", "odds_draw", "odds_away"]


def kelly_fraction(prob: float, odds: float, fraction: float = 0.25, max_stake: float = 0.02) -> float:
    if odds <= 1:
        return 0.0
    full = (prob * odds - 1) / (odds - 1)
    return float(min(max(full * fraction, 0.0), max_stake))


def simulate(
    df: pd.DataFrame,
    probs: np.ndarray,
    min_confidence: float,
    min_edge: float = 0.03,
    initial_bankroll: float = 1000.0,
) -> tuple[pd.DataFrame, dict]:
    bankroll = initial_bankroll
    peak = bankroll
    records = []

    odds = df[ODDS_COLS].apply(pd.to_numeric, errors="coerce").to_numpy()
    valid = np.isfinite(odds).all(axis=1) & (odds > 1).all(axis=1)

    for i, row in enumerate(df.itertuples(index=False)):
        if not valid[i]:
            continue
        best_side = int(np.argmax(probs[i] * odds[i] - 1))
        prob = float(probs[i, best_side])
        price = float(odds[i, best_side])
        edge = prob - (1 / price)
        if prob < min_confidence or edge < min_edge:
            continue
        stake = bankroll * kelly_fraction(prob, price)
        if stake < 0.01:
            continue
        won = int(row.outcome) == best_side
        profit = stake * (price - 1) if won else -stake
        bankroll += profit
        peak = max(peak, bankroll)
        records.append({
            "date": row.date,
            "league": row.league,
            "home_team": row.home_team,
            "away_team": row.away_team,
            "bet_side": best_side,
            "prob": prob,
            "odds": price,
            "edge": edge,
            "stake": stake,
            "profit": profit,
            "bankroll": bankroll,
            "won": won,
            "drawdown": bankroll / peak - 1,
        })

    bets = pd.DataFrame(records)
    if bets.empty:
        return bets, {
            "n_bets": 0,
            "roi_pct": 0.0,
            "final_bankroll": round(initial_bankroll, 2),
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
        }
    stats = {
        "n_bets": int(len(bets)),
        "roi_pct": round(float(100 * bets["profit"].sum() / bets["stake"].sum()), 2),
        "final_bankroll": round(float(bankroll), 2),
        "max_drawdown_pct": round(float(100 * bets["drawdown"].min()), 2),
        "win_rate_pct": round(float(100 * bets["won"].mean()), 2),
        "avg_odds": round(float(bets["odds"].mean()), 3),
        "avg_edge_pct": round(float(100 * bets["edge"].mean()), 2),
    }
    return bets, stats


def threshold_curve(df: pd.DataFrame, probs: np.ndarray, thresholds=None) -> list[dict]:
    thresholds = thresholds or [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    out = []
    for threshold in thresholds:
        _, stats = simulate(df, probs, min_confidence=threshold)
        out.append({"threshold": threshold, **stats})
    return out
