from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtesting import simulate, threshold_curve
from src.modeling import elo_probabilities, fit_lgbm, metrics, temporal_split, tune_blend
from src.pipeline import FEATURE_COLS, build_features

OUT = Path(__file__).resolve().parents[1] / "data" / "predictions.json"
LABELS = ["H", "D", "A"]


def main() -> None:
    df = build_features()
    train, val, test = temporal_split(df)
    model = fit_lgbm(train)

    pe_val = elo_probabilities(train, val)
    pe_test = elo_probabilities(train, test)
    pm_val = model.predict_proba(val[FEATURE_COLS])
    pm_test = model.predict_proba(test[FEATURE_COLS])
    weight = tune_blend(val["outcome"].to_numpy(), pm_val, pe_val)
    pb_val = weight * pm_val + (1 - weight) * pe_val
    pb_test = weight * pm_test + (1 - weight) * pe_test

    val_curve = threshold_curve(val, pb_val)
    candidates = [row for row in val_curve if row["n_bets"] >= 80]
    threshold = max(candidates, key=lambda r: (r["final_bankroll"], r["roi_pct"]))["threshold"] if candidates else 0.6
    _, val_backtest = simulate(val, pb_val, min_confidence=threshold)
    bets, test_backtest = simulate(test, pb_test, min_confidence=threshold)

    recent = test.tail(40).copy()
    pe_recent = elo_probabilities(train, recent)
    pm_recent = model.predict_proba(recent[FEATURE_COLS])
    pb_recent = weight * pm_recent + (1 - weight) * pe_recent
    matches = []
    for i, row in enumerate(recent.itertuples(index=False)):
        probs = pb_recent[i]
        pred = int(probs.argmax())
        matches.append({
            "date": row.date.strftime("%Y-%m-%d"),
            "league": row.league_name,
            "home": row.home_team,
            "away": row.away_team,
            "p_home": round(float(probs[0]), 3),
            "p_draw": round(float(probs[1]), 3),
            "p_away": round(float(probs[2]), 3),
            "pred_outcome": LABELS[pred],
            "actual_outcome": LABELS[int(row.outcome)],
            "actual_score": f"{int(row.home_goals)}-{int(row.away_goals)}",
            "correct": pred == int(row.outcome),
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Club Elo + rolling form/shots + LightGBM, blend tuned on temporal validation",
        "data_source": "football-data.co.uk CSV, Big Five leagues, seasons 2015-2016 to 2025-2026",
        "n_matches": int(len(df)),
        "blend_weight": round(weight, 2),
        "selected_threshold": threshold,
        "validation_metrics": {
            "elo": metrics(val["outcome"].to_numpy(), pe_val),
            "ml": metrics(val["outcome"].to_numpy(), pm_val),
            "blend": metrics(val["outcome"].to_numpy(), pb_val),
        },
        "test_metrics": {
            "elo": metrics(test["outcome"].to_numpy(), pe_test),
            "ml": metrics(test["outcome"].to_numpy(), pm_test),
            "blend": metrics(test["outcome"].to_numpy(), pb_test),
        },
        "backtest": {
            "validation": val_backtest,
            "test": test_backtest,
            "threshold_curve_validation": val_curve,
        },
        "recent_matches": matches,
        "recent_bets": [] if bets.empty else bets.tail(20).assign(date=lambda x: x["date"].dt.strftime("%Y-%m-%d")).to_dict("records"),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Ecrit {OUT}")
    print(payload["test_metrics"])
    print(payload["backtest"]["test"])


if __name__ == "__main__":
    main()
