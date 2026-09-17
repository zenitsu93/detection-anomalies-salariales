# -*- coding: utf-8 -*-
"""
Tests de bucket_anciennete() : la fonction qui transforme une anciennete (en annees) en tranche
("0-2", "3-5", "6-12", "13-20", ">20"), pour regrouper les salaries ayant une anciennete comparable
dans un meme groupe de comparaison.
"""

import pytest

from anomaly_core import bucket_anciennete


@pytest.mark.parametrize(
    "annees, tranche_attendue",
    [
        (0, "0-2"),
        (1, "0-2"),
        (2, "0-2"),        # limite haute de la tranche "0-2" : incluse
        (2.5, "3-5"),      # juste au-dessus : bascule dans la tranche suivante
        (3, "3-5"),
        (5, "3-5"),        # limite haute de "3-5" : incluse
        (5.5, "6-12"),
        (6, "6-12"),
        (12, "6-12"),      # limite haute de "6-12" : incluse
        (12.5, "13-20"),
        (13, "13-20"),
        (20, "13-20"),     # limite haute de "13-20" : incluse
        (20.5, ">20"),
        (21, ">20"),
        (40, ">20"),
    ],
)
def test_chaque_tranche_d_anciennete_est_correctement_attribuee(annees, tranche_attendue):
    """Verifie, annee par annee (y compris exactement aux frontieres entre deux tranches), que
    chaque anciennete tombe dans la bonne tranche. C'est le test le plus important de ce fichier :
    une erreur de frontiere ferait glisser des salaries dans le mauvais groupe de comparaison."""
    assert bucket_anciennete(annees) == tranche_attendue


@pytest.mark.parametrize("valeur_invalide", ["texte", None, "", object()])
def test_anciennete_illisible_donne_na_sans_planter(valeur_invalide):
    """Si l'anciennete n'est pas un nombre exploitable (texte, valeur vide, case manquante...), la
    fonction doit renvoyer "NA" au lieu de faire planter le programme."""
    assert bucket_anciennete(valeur_invalide) == "NA"


def test_anciennete_donnee_sous_forme_de_texte_numerique_fonctionne_quand_meme():
    """Une anciennete lue depuis un fichier CSV peut arriver sous forme de texte (ex: "7" au lieu
    du nombre 7). La fonction doit quand meme reussir a la convertir et a la classer correctement."""
    assert bucket_anciennete("7") == "6-12"
