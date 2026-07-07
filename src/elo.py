from __future__ import annotations

import math
from dataclasses import dataclass, field

HOME_ADVANTAGE = 55.0
INITIAL_ELO = 1500.0


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def margin_multiplier(goal_diff: int) -> float:
    diff = abs(goal_diff)
    if diff <= 1:
        return 1.0
    return math.log(diff + 1) * 1.35


@dataclass
class ClubElo:
    initial: float = INITIAL_ELO
    k: float = 22.0
    ratings: dict[str, float] = field(default_factory=dict)

    def get(self, team: str) -> float:
        return self.ratings.get(team, self.initial)

    def pre_match(self, home: str, away: str) -> tuple[float, float, float]:
        home_elo = self.get(home)
        away_elo = self.get(away)
        return home_elo, away_elo, home_elo + HOME_ADVANTAGE - away_elo

    def update(self, home: str, away: str, home_goals: int, away_goals: int) -> None:
        home_elo, away_elo = self.get(home), self.get(away)
        expected_home = expected_score(home_elo + HOME_ADVANTAGE, away_elo)
        if home_goals > away_goals:
            actual_home = 1.0
        elif home_goals == away_goals:
            actual_home = 0.5
        else:
            actual_home = 0.0
        delta = self.k * margin_multiplier(home_goals - away_goals) * (actual_home - expected_home)
        self.ratings[home] = home_elo + delta
        self.ratings[away] = away_elo - delta
