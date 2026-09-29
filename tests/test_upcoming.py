import pandas as pd

from src.upcoming import elo_actuels, lire_fixtures, predire

FIXTURES = (
    "﻿Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA\n"
    "EC,29/09/2026,19:45,Barrow,Scunthorpe,2.02,3.4,3.6\n"
    "F1,03/10/2026,21:00,Paris SG,Lens,1.40,4.8,7.5\n"
    "E0,03/10/2026,16:00,Arsenal,Chelsea,,,\n"
)


def _historique() -> pd.DataFrame:
    lignes = []
    for i in range(30):
        lignes.append({"league": "F1", "HomeTeam": "Paris SG", "AwayTeam": "Lens", "FTHG": 3, "FTAG": 0})
        lignes.append({"league": "E0", "HomeTeam": "Chelsea", "AwayTeam": "Arsenal", "FTHG": 1, "FTAG": 1})
    return pd.DataFrame(lignes)


def _features() -> pd.DataFrame:
    return pd.DataFrame({
        "elo_diff": [-200, -50, 0, 50, 100, 200, 300] * 20,
        "home_goals": [0, 1, 1, 2, 2, 3, 3] * 20,
        "away_goals": [2, 1, 1, 1, 0, 1, 0] * 20,
    })


def test_seules_les_ligues_suivies_sont_gardees():
    fixtures = lire_fixtures(FIXTURES.lstrip("﻿"), {"F1", "E0"})
    assert list(fixtures["Div"]) == ["F1", "E0"]
    assert fixtures.loc[0, "date"] == pd.Timestamp(2026, 10, 3)


def test_elo_rejoue_par_ligue():
    elos = elo_actuels(_historique())
    assert elos["F1"].get("Paris SG") > elos["F1"].get("Lens")
    assert elos["E0"].get("Paris SG") == elos["E0"].initial


def test_pronostic_elo_et_marche():
    fixtures = lire_fixtures(FIXTURES, {"F1", "E0"})
    matchs = predire(fixtures, _features(), elo_actuels(_historique()), {"F1": "Ligue 1", "E0": "Premier League"})
    psg = next(m for m in matchs if m["home"] == "Paris SG")
    assert psg["pred_outcome"] == "H"
    assert abs(psg["p_home"] + psg["p_draw"] + psg["p_away"] - 1) < 0.01
    assert psg["league_name"] == "Ligue 1" and psg["method"] == "elo"
    assert abs(psg["market_home"] - (1 / 1.40) / (1 / 1.40 + 1 / 4.8 + 1 / 7.5)) < 0.001
    arsenal = next(m for m in matchs if m["home"] == "Arsenal")
    assert "market_home" not in arsenal


def test_calendrier_vide():
    assert predire(pd.DataFrame(), _features(), {}, {}) == []
