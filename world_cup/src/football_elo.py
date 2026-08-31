"""
Elo pour le football international (méthode World Football Elo Ratings).

- Avantage du terrain : bonus Elo appliqué à l'équipe à domicile (0 si terrain neutre).
- Importance du match : K pondéré par le type de tournoi (Coupe du monde > continental
  > qualifs > amical).
- Marge de victoire : le gain Elo croît avec l'écart de buts (multiplicateur).

Ratings calculés chronologiquement : à chaque match, l'état AVANT le match est
enregistré, donc utilisable pour une prédiction sans fuite d'information.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# Poids d'importance (K de base) par type de tournoi.
TOURNAMENT_K = {
    "fifa world cup": 60.0,
    "uefa euro": 50.0,
    "copa américa": 50.0,
    "african cup of nations": 50.0,
    "afc asian cup": 50.0,
    "confederations cup": 45.0,
    "uefa nations league": 40.0,
    "fifa world cup qualification": 40.0,
    "uefa euro qualification": 35.0,
    "friendly": 20.0,
}
DEFAULT_K = 30.0
HOME_ADVANTAGE = 65.0   # points Elo ajoutés à l'équipe à domicile


def k_for_tournament(tournament: str) -> float:
    t = (tournament or "").lower()
    # Clés parcourues de la plus spécifique à la plus générale : sans ce tri,
    # "fifa world cup" capture aussi "fifa world cup qualification", dont le K
    # plus faible n'était jamais atteint.
    for key, k in sorted(TOURNAMENT_K.items(), key=lambda item: -len(item[0])):
        if key in t:
            return k
    return DEFAULT_K


def mov_multiplier(goal_diff: int) -> float:
    """Multiplicateur de marge de victoire (World Football Elo)."""
    g = abs(goal_diff)
    if g <= 1:
        return 1.0
    if g == 2:
        return 1.5
    return (11 + g) / 8.0   # g=3 -> 1.75, g=4 -> 1.875, ...


def expected_score(elo_a: float, elo_b: float) -> float:
    """Probabilité de non-défaite pondérée (score attendu Elo) de A contre B."""
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


@dataclass
class FootballElo:
    initial: float = 1500.0
    ratings: dict = field(default_factory=dict)

    def get(self, team: str) -> float:
        return self.ratings.get(team, self.initial)

    def pre_match(self, home: str, away: str, neutral: bool) -> tuple[float, float, float]:
        """Retourne (elo_home, elo_away, elo_diff_ajusté du domicile) AVANT le match."""
        eh, ea = self.get(home), self.get(away)
        adv = 0.0 if neutral else HOME_ADVANTAGE
        return eh, ea, (eh + adv) - ea

    def update(self, home: str, away: str, hs: int, as_: int, tournament: str, neutral: bool) -> None:
        eh, ea = self.get(home), self.get(away)
        adv = 0.0 if neutral else HOME_ADVANTAGE
        we_home = expected_score(eh + adv, ea)
        if hs > as_:
            w_home = 1.0
        elif hs < as_:
            w_home = 0.0
        else:
            w_home = 0.5
        k = k_for_tournament(tournament) * mov_multiplier(hs - as_)
        delta = k * (w_home - we_home)
        self.ratings[home] = eh + delta
        self.ratings[away] = ea - delta
