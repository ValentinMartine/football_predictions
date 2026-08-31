"""Invariants de la baseline Elo clubs.

Ces tests protègent les propriétés dont dépendent le blend et le backtest :
symétrie, monotonie, conservation des points et absence de fuite temporelle.
"""

from src.elo import HOME_ADVANTAGE, ClubElo, expected_score, margin_multiplier


class TestExpectedScore:
    def test_deux_equipes_egales_donnent_une_chance_sur_deux(self):
        assert expected_score(1500.0, 1500.0) == 0.5

    def test_les_probabilites_des_deux_camps_somment_a_un(self):
        assert expected_score(1700.0, 1500.0) + expected_score(1500.0, 1700.0) == 1.0

    def test_la_probabilite_croit_avec_l_ecart_de_niveau(self):
        ecarts = [expected_score(1500.0 + e, 1500.0) for e in (0, 50, 100, 400)]
        assert ecarts == sorted(ecarts)
        assert ecarts[-1] > 0.9

    def test_quatre_cents_points_d_ecart_valent_dix_contre_un(self):
        assert round(expected_score(1900.0, 1500.0), 4) == round(10 / 11, 4)


class TestMarginMultiplier:
    def test_un_but_d_ecart_ne_modifie_pas_le_k(self):
        assert margin_multiplier(0) == 1.0
        assert margin_multiplier(1) == 1.0
        assert margin_multiplier(-1) == 1.0

    def test_le_multiplicateur_est_symetrique_par_signe(self):
        assert margin_multiplier(3) == margin_multiplier(-3)

    def test_le_multiplicateur_croit_avec_l_ecart_de_buts(self):
        valeurs = [margin_multiplier(d) for d in range(1, 7)]
        assert valeurs == sorted(valeurs)
        assert all(v >= 1.0 for v in valeurs)


class TestClubElo:
    def test_une_equipe_inconnue_part_de_l_elo_initial(self):
        elo = ClubElo()
        assert elo.get("Nouveau club") == elo.initial

    def test_le_pre_match_applique_l_avantage_du_terrain(self):
        elo = ClubElo()
        domicile, exterieur, ecart = elo.pre_match("A", "B")
        assert domicile == exterieur == elo.initial
        assert ecart == HOME_ADVANTAGE

    def test_la_somme_des_elo_est_conservee(self):
        elo = ClubElo()
        elo.ratings.update({"A": 1600.0, "B": 1400.0})
        avant = elo.get("A") + elo.get("B")
        elo.update("A", "B", 3, 1)
        assert round(elo.get("A") + elo.get("B"), 9) == round(avant, 9)

    def test_le_vainqueur_monte_et_le_perdant_descend(self):
        elo = ClubElo()
        elo.update("A", "B", 2, 0)
        assert elo.get("A") > elo.initial
        assert elo.get("B") < elo.initial

    def test_un_nul_penalise_l_equipe_a_domicile(self):
        # À niveau égal, l'avantage du terrain fait du nul un résultat décevant.
        elo = ClubElo()
        elo.update("A", "B", 1, 1)
        assert elo.get("A") < elo.initial
        assert elo.get("B") > elo.initial

    def test_une_victoire_large_rapporte_plus_qu_une_victoire_courte(self):
        courte, large = ClubElo(), ClubElo()
        courte.update("A", "B", 1, 0)
        large.update("A", "B", 5, 0)
        assert large.get("A") > courte.get("A")


class TestAbsenceDeFuite:
    def test_l_elo_pre_match_ignore_les_matchs_posterieurs(self):
        # L'Elo lu avant le match N doit être identique, que les matchs suivants
        # existent ou non : c'est ce qui garantit un backtest honnête.
        elo = ClubElo()
        elo.update("A", "B", 2, 0)
        elo.update("B", "A", 1, 0)
        reference = elo.pre_match("A", "B")

        rejeu = ClubElo()
        rejeu.update("A", "B", 2, 0)
        rejeu.update("B", "A", 1, 0)
        avant = rejeu.pre_match("A", "B")
        rejeu.update("A", "B", 4, 0)  # match postérieur, ne doit rien changer

        assert avant == reference

    def test_l_ordre_chronologique_change_le_resultat(self):
        # Garde-fou : si l'ordre n'avait aucun effet, la passe ne serait pas chronologique.
        croissant, decroissant = ClubElo(), ClubElo()
        for domicile, exterieur, bd, be in (("A", "B", 3, 0), ("A", "B", 0, 1)):
            croissant.update(domicile, exterieur, bd, be)
        for domicile, exterieur, bd, be in (("A", "B", 0, 1), ("A", "B", 3, 0)):
            decroissant.update(domicile, exterieur, bd, be)
        assert croissant.get("A") != decroissant.get("A")
