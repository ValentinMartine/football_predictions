"""Prochains matchs des cinq grands championnats, d'après le fixtures.csv de football-data.co.uk.

Probabilités de l'Elo seul : les variables de forme du LightGBM demandent le match joué, et
les calculer à l'avance changerait le pipeline validé. Le site et l'alerte Telegram l'affichent
donc comme un pronostic Elo, à côté de la cote moyenne du marché.
"""
from __future__ import annotations

import io
import urllib.request
from collections import defaultdict

import pandas as pd

from src.elo import ClubElo
from src.modeling import elo_probabilities

FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
ISSUES = ("H", "D", "A")


def telecharger_fixtures(url: str = FIXTURES_URL, delai: int = 30) -> str:
    requete = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return reponse.read().decode("utf-8-sig")


def lire_fixtures(texte: str, ligues: set[str]) -> pd.DataFrame:
    fixtures = pd.read_csv(io.StringIO(texte))
    if fixtures.empty or "Div" not in fixtures:
        return fixtures.iloc[0:0]
    fixtures = fixtures[fixtures["Div"].isin(ligues)].copy()
    fixtures["date"] = pd.to_datetime(fixtures["Date"], dayfirst=True)
    return fixtures.reset_index(drop=True)


def elo_actuels(matches: pd.DataFrame) -> dict[str, ClubElo]:
    """Elo de fin d'historique, rejoué dans le même ordre et la même classe que build_features."""
    elos: dict[str, ClubElo] = defaultdict(ClubElo)
    for row in matches.itertuples(index=False):
        elos[str(row.league)].update(str(row.HomeTeam), str(row.AwayTeam), int(row.FTHG), int(row.FTAG))
    return elos


def _marche(ligne) -> dict | None:
    cotes = [ligne.get(f"Avg{issue}") for issue in ISSUES]
    if any(pd.isna(c) or not c for c in cotes):
        return None
    brutes = [1 / float(c) for c in cotes]
    total = sum(brutes)
    return {f"market_{nom}": round(b / total, 3) for nom, b in zip(("home", "draw", "away"), brutes)}


def predire(fixtures: pd.DataFrame, features: pd.DataFrame, elos: dict[str, ClubElo],
            noms_ligues: dict[str, str]) -> list[dict]:
    if fixtures.empty:
        return []
    lignes = []
    for f in fixtures.to_dict("records"):
        elo_home, elo_away, elo_diff = elos[f["Div"]].pre_match(f["HomeTeam"], f["AwayTeam"])
        lignes.append({**f, "elo_home": elo_home, "elo_away": elo_away, "elo_diff": elo_diff})
    avec_elo = pd.DataFrame(lignes)
    probas = elo_probabilities(features, avec_elo)
    matchs = []
    for f, p in zip(lignes, probas):
        issue = int(p.argmax())
        match = {
            "date": f["date"].strftime("%Y-%m-%d"),
            "time": str(f.get("Time") or ""),
            "league": f["Div"],
            "league_name": noms_ligues.get(f["Div"], f["Div"]),
            "home": f["HomeTeam"],
            "away": f["AwayTeam"],
            "p_home": round(float(p[0]), 3),
            "p_draw": round(float(p[1]), 3),
            "p_away": round(float(p[2]), 3),
            "pred_outcome": ISSUES[issue],
            "method": "elo",
            "elo_home": round(f["elo_home"], 1),
            "elo_away": round(f["elo_away"], 1),
        }
        match.update(_marche(f) or {})
        matchs.append(match)
    return sorted(matchs, key=lambda m: (m["date"], m["time"], m["league"], m["home"]))
