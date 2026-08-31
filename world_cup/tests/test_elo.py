"""Invariants de l'Elo international.

Protège la hiérarchie des K par tournoi, la marge de victoire, l'avantage du
terrain sur terrain neutre et l'absence de fuite temporelle.
"""

from src.football_elo import (
    DEFAULT_K,
    HOME_ADVANTAGE,
    FootballElo,
    expected_score,
    k_for_tournament,
    mov_multiplier,
)


class TestExpectedScore:
    def test_deux_selections_egales_donnent_une_chance_sur_deux(self):
        assert expected_score(1500.0, 1500.0) == 0.5

    def test_les_probabilites_des_deux_camps_somment_a_un(self):
        assert expected_score(1800.0, 1500.0) + expected_score(1500.0, 1800.0) == 1.0

    def test_la_probabilite_croit_avec_l_ecart_de_niveau(self):
        valeurs = [expected_score(1500.0 + e, 1500.0) for e in (0, 100, 200, 400)]
        assert valeurs == sorted(valeurs)


class TestKParTournoi:
    def test_un_tournoi_inconnu_retombe_sur_le_k_par_defaut(self):
        assert k_for_tournament("Tournoi inventé") == DEFAULT_K
        assert k_for_tournament("") == DEFAULT_K
        assert k_for_tournament(None) == DEFAULT_K

    def test_la_coupe_du_monde_pese_plus_qu_un_amical(self):
        assert k_for_tournament("FIFA World Cup") > k_for_tournament("Friendly")

    def test_la_reconnaissance_du_tournoi_ignore_la_casse(self):
        assert k_for_tournament("fifa world cup") == k_for_tournament("FIFA World Cup")

    def test_une_qualification_pese_moins_que_la_phase_finale(self):
        assert k_for_tournament("FIFA World Cup qualification") < k_for_tournament("FIFA World Cup")


class TestMovMultiplier:
    def test_un_but_d_ecart_ne_modifie_pas_le_k(self):
        assert mov_multiplier(0) == 1.0
        assert mov_multiplier(1) == 1.0

    def test_le_multiplicateur_est_symetrique_par_signe(self):
        assert mov_multiplier(3) == mov_multiplier(-3)

    def test_le_multiplicateur_croit_avec_l_ecart_de_buts(self):
        valeurs = [mov_multiplier(g) for g in range(1, 8)]
        assert valeurs == sorted(valeurs)
        assert all(v >= 1.0 for v in valeurs)


class TestFootballElo:
    def test_une_selection_inconnue_part_de_l_elo_initial(self):
        assert FootballElo().get("Inconnue") == 1500.0

    def test_le_terrain_neutre_annule_l_avantage_du_domicile(self):
        elo = FootballElo()
        _, _, ecart_domicile = elo.pre_match("A", "B", neutral=False)
        _, _, ecart_neutre = elo.pre_match("A", "B", neutral=True)
        assert ecart_domicile == HOME_ADVANTAGE
        assert ecart_neutre == 0.0

    def test_la_somme_des_elo_est_conservee(self):
        elo = FootballElo()
        elo.ratings.update({"A": 1700.0, "B": 1450.0})
        avant = elo.get("A") + elo.get("B")
        elo.update("A", "B", 2, 1, "FIFA World Cup", neutral=True)
        assert round(elo.get("A") + elo.get("B"), 9) == round(avant, 9)

    def test_le_vainqueur_monte_et_le_perdant_descend(self):
        elo = FootballElo()
        elo.update("A", "B", 1, 0, "Friendly", neutral=True)
        assert elo.get("A") > 1500.0
        assert elo.get("B") < 1500.0

    def test_une_victoire_en_coupe_du_monde_rapporte_plus_qu_en_amical(self):
        mondial, amical = FootballElo(), FootballElo()
        mondial.update("A", "B", 1, 0, "FIFA World Cup", neutral=True)
        amical.update("A", "B", 1, 0, "Friendly", neutral=True)
        assert mondial.get("A") > amical.get("A")

    def test_un_nul_sur_terrain_neutre_entre_egaux_ne_change_rien(self):
        elo = FootballElo()
        elo.update("A", "B", 0, 0, "Friendly", neutral=True)
        assert elo.get("A") == elo.get("B") == 1500.0


class TestAbsenceDeFuite:
    def test_l_elo_pre_match_ignore_les_matchs_posterieurs(self):
        elo = FootballElo()
        elo.update("A", "B", 2, 0, "Friendly", neutral=True)
        avant = elo.pre_match("A", "B", neutral=True)
        elo.update("A", "B", 5, 0, "FIFA World Cup", neutral=True)
        rejeu = FootballElo()
        rejeu.update("A", "B", 2, 0, "Friendly", neutral=True)
        assert rejeu.pre_match("A", "B", neutral=True) == avant
