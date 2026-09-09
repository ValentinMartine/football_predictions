"""Archivage daté des données de marché, et lecture sans fuite temporelle.

Transfermarkt et Capology ne servent que le présent : sans archive, chaque exécution
détruit l'état précédent. Ces tests protègent la propriété dont dépendra la feature,
à savoir qu'un match ne voie jamais une valeur d'effectif postérieure à sa date.
"""

import json
from datetime import date

import pytest

from scripts.fetch_market_data import archiver, charger_historique, valeurs_a_la_date


def _payload(valeur):
    return {
        "source": "test",
        "teams": {"bayern munich": {"value_meur": valeur, "squad": 23, "avg_age": 27.3}},
    }


@pytest.fixture
def historique(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.fetch_market_data.HISTORIQUE", tmp_path)
    return tmp_path


class TestArchiver:
    def test_le_fichier_porte_la_date_de_capture(self, historique):
        chemin = archiver(_payload(1040.0), jour=date(2026, 9, 5))
        assert chemin.name == "2026-09-05.json"
        assert json.loads(chemin.read_text(encoding="utf-8"))["captured_on"] == "2026-09-05"

    def test_le_contenu_original_est_conserve(self, historique):
        chemin = archiver(_payload(1040.0), jour=date(2026, 9, 5))
        archive = json.loads(chemin.read_text(encoding="utf-8"))
        assert archive["teams"]["bayern munich"]["value_meur"] == 1040.0
        assert archive["source"] == "test"

    def test_deux_executions_le_meme_jour_ecrasent_le_meme_instantane(self, historique):
        archiver(_payload(1040.0), jour=date(2026, 9, 5))
        archiver(_payload(1055.0), jour=date(2026, 9, 5))
        assert len(list(historique.glob("*.json"))) == 1
        assert valeurs_a_la_date("2026-09-05", historique)["bayern munich"]["value_meur"] == 1055.0

    def test_deux_jours_donnent_deux_instantanes(self, historique):
        archiver(_payload(1040.0), jour=date(2026, 9, 5))
        archiver(_payload(1055.0), jour=date(2026, 9, 12))
        assert sorted(p.stem for p in historique.glob("*.json")) == ["2026-09-05", "2026-09-12"]

    def test_le_repertoire_est_cree_au_besoin(self, tmp_path, monkeypatch):
        cible = tmp_path / "absent" / "market_history"
        monkeypatch.setattr("scripts.fetch_market_data.HISTORIQUE", cible)
        assert archiver(_payload(1.0)).exists()


class TestValeursALaDate:
    def test_la_date_exacte_renvoie_son_instantane(self, historique):
        archiver(_payload(1040.0), jour=date(2026, 9, 5))
        assert valeurs_a_la_date("2026-09-05", historique)["bayern munich"]["value_meur"] == 1040.0

    def test_un_match_lit_le_dernier_instantane_anterieur(self, historique):
        archiver(_payload(1040.0), jour=date(2026, 9, 5))
        archiver(_payload(1055.0), jour=date(2026, 9, 12))
        assert valeurs_a_la_date("2026-09-09", historique)["bayern munich"]["value_meur"] == 1040.0

    def test_aucune_valeur_posterieure_au_match_n_est_visible(self, historique):
        """La regle cardinale du depot : pas de fuite temporelle."""
        archiver(_payload(1055.0), jour=date(2026, 9, 12))
        assert valeurs_a_la_date("2026-09-09", historique) == {}

    def test_historique_absent(self, tmp_path):
        assert valeurs_a_la_date("2026-09-09", tmp_path / "vide") == {}
        assert charger_historique(tmp_path / "vide") == {}

    def test_historique_ordonne_du_plus_ancien_au_plus_recent(self, historique):
        for jour in (date(2026, 9, 12), date(2026, 9, 5), date(2026, 9, 19)):
            archiver(_payload(1.0), jour=jour)
        assert list(charger_historique(historique)) == ["2026-09-05", "2026-09-12", "2026-09-19"]
