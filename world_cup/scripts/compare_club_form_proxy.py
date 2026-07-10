from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FORM = ROOT.parents[0] / "football_clubs_predictions" / "data" / "national_player_form.json"
PREDICTIONS = ROOT / "data" / "predictions.json"
OUT = ROOT / "data" / "club_form_proxy_report.json"

ALIASES = {
    "United States": "USA",
    "Iran": "IR IRAN",
    "South Korea": "KOREA REPUBLIC",
}


def _key(team: str | None) -> str | None:
    if team is None:
        return None
    return ALIASES.get(team, team).upper()


def _score(country: dict | None) -> float | None:
    if not country:
        return None
    # xG+xA carries attacking contribution; minutes stabilize countries with larger elite pools.
    return float(country["xg_xa"]) + 0.002 * math.sqrt(float(country["minutes"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--national-form", type=Path, default=DEFAULT_FORM)
    args = parser.parse_args()

    form = json.loads(args.national_form.read_text(encoding="utf-8"))
    predictions = json.loads(PREDICTIONS.read_text(encoding="utf-8"))
    countries = {
        _key(row.get("team")): row
        for row in form["countries"]
        if row.get("team")
    }

    rows = []
    covered = 0
    proxy_correct = 0
    comparable = 0
    for match in predictions["wc_matches"]:
        home = countries.get(_key(match["home"]))
        away = countries.get(_key(match["away"]))
        home_score = _score(home)
        away_score = _score(away)
        proxy = None
        correct = None
        if home_score is not None and away_score is not None:
            covered += 1
            if abs(home_score - away_score) >= 1.0:
                proxy = "H" if home_score > away_score else "A"
                comparable += 1
                correct = proxy == match["actual_outcome"]
                proxy_correct += int(correct)
        rows.append({
            "date": match["date"],
            "home": match["home"],
            "away": match["away"],
            "home_form_score": round(home_score, 2) if home_score is not None else None,
            "away_form_score": round(away_score, 2) if away_score is not None else None,
            "proxy_pick": proxy,
            "actual_outcome": match["actual_outcome"],
            "proxy_correct": correct,
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(args.national_form),
        "definition": "National-player-pool proxy from Big Five club xG+xA and minutes, not official roster strength.",
        "coverage": {
            "wc_matches": len(predictions["wc_matches"]),
            "both_teams_covered": covered,
            "proxy_comparable_matches": comparable,
        },
        "metrics": {
            "proxy_accuracy_when_comparable": round(proxy_correct / comparable, 4) if comparable else None,
            "baseline_blend_wc_accuracy": predictions["wc_metrics"]["accuracy"],
            "baseline_blend_wc_log_loss": predictions["wc_metrics"]["log_loss"],
        },
        "decision": (
            "candidate_only: this proxy is not activated in the main model until official squad lists "
            "and historical roster snapshots are joined without leakage."
        ),
        "matches": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"écrit {OUT}")
    print(payload["coverage"])
    print(payload["metrics"])


if __name__ == "__main__":
    main()
