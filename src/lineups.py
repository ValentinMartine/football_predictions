from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class TeamLineup:
    team: str
    formation: str | None = None
    starters: list[str] = field(default_factory=list)
    substitutes: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MatchLineupSnapshot:
    source: str
    fetched_at: str
    home: TeamLineup
    away: TeamLineup


def lineup_adjusted_prediction(initial_probs: np.ndarray, snapshot: MatchLineupSnapshot | None) -> tuple[np.ndarray, dict]:
    """Return late pre-match probabilities when official lineup data is available.

    The adjustment is intentionally neutral until a stable source of official
    lineups, formations, absences and player-minute load is connected.
    """
    if snapshot is None:
        return initial_probs, {
            "status": "not_available",
            "reason": "Official lineups/formations are not connected yet.",
        }
    return initial_probs, {
        "status": "neutral_passthrough",
        "source": snapshot.source,
        "fetched_at": snapshot.fetched_at,
        "home_formation": snapshot.home.formation,
        "away_formation": snapshot.away.formation,
        "home_starters": len(snapshot.home.starters),
        "away_starters": len(snapshot.away.starters),
        "home_unavailable": len(snapshot.home.unavailable),
        "away_unavailable": len(snapshot.away.unavailable),
        "reason": "Lineup schema is present; model weights will be trained only after historical coverage is available.",
    }
