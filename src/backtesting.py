from __future__ import annotations

import numpy as np
import pandas as pd

ODDS_COLS = ["odds_home", "odds_draw", "odds_away"]
ROBUST_POLICY = {
    "threshold": 0.50,
    "min_edge": 0.10,
    "min_odds": 1.80,
    "max_odds": 3.00,
    "source": "fixed_walk_forward",
}


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
    min_odds: float = 1.2,
    max_odds: float = 4.0,
    kelly_fraction_value: float = 0.25,
    max_stake: float = 0.02,
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
        expected_value = prob * price - 1
        implied_probability = 1 / price
        probability_edge = prob - implied_probability
        if prob < min_confidence or expected_value < min_edge or price < min_odds or price > max_odds:
            continue
        stake = bankroll * kelly_fraction(prob, price, fraction=kelly_fraction_value, max_stake=max_stake)
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
            "expected_value": expected_value,
            "edge": expected_value,
            "probability_edge": probability_edge,
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
        "avg_ev_pct": round(float(100 * bets["expected_value"].mean()), 2),
        "avg_edge_pct": round(float(100 * bets["expected_value"].mean()), 2),
        "total_staked": round(float(bets["stake"].sum()), 2),
        "total_profit": round(float(bets["profit"].sum()), 2),
    }
    return bets, stats


def threshold_curve(
    df: pd.DataFrame,
    probs: np.ndarray,
    thresholds=None,
    min_edges=None,
    odds_ranges=None,
    min_bets: int = 0,
) -> list[dict]:
    thresholds = thresholds or [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    min_edges = min_edges or [0.00, 0.04, 0.08, 0.10, 0.12, 0.15]
    odds_ranges = odds_ranges or [(1.2, 4.0), (1.4, 3.0), (1.5, 2.5), (1.6, 2.3), (1.8, 3.0)]
    out = []
    for threshold in thresholds:
        for min_edge in min_edges:
            for min_odds, max_odds in odds_ranges:
                _, stats = simulate(
                    df,
                    probs,
                    min_confidence=threshold,
                    min_edge=min_edge,
                    min_odds=min_odds,
                    max_odds=max_odds,
                )
                if stats["n_bets"] >= min_bets:
                    out.append({
                        "threshold": threshold,
                        "min_edge": min_edge,
                        "min_odds": min_odds,
                        "max_odds": max_odds,
                        **stats,
                    })
    return out


def select_policy(curve: list[dict], min_bets: int = 100) -> dict:
    candidates = [row for row in curve if row["n_bets"] >= min_bets]
    if not candidates:
        candidates = curve
    if not candidates:
        return ROBUST_POLICY.copy()
    return max(candidates, key=lambda r: (r["final_bankroll"], r["roi_pct"], r["n_bets"]))
