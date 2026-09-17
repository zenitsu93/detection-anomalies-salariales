# -*- coding: utf-8 -*-
"""
Tests de robust_zscore() : la fonction qui dit "a quel point ce salaire est-il different
des autres, dans son groupe de comparaison ?"

Idee generale (en langage simple) : on prend le salaire "du milieu" (la mediane) du groupe, et on
regarde de combien chaque salarie s'en ecarte, en tenant compte de la dispersion habituelle du
groupe. Un score proche de 0 = salaire dans la norme du groupe. Un score tres eloigne de 0
(largement au-dessus de 2 ou 3 en valeur absolue) = salarie qui se demarque nettement.
"""

import numpy as np
import pandas as pd

from anomaly_core import robust_zscore


def test_un_salarie_tres_different_des_autres_ressort_nettement():
    """Verifie l'objectif principal de la fonction : si 9 salaries ont un salaire proche les uns
    des autres et qu'un dixieme gagne beaucoup plus, ce dixieme doit obtenir un score tres eloigne
    de 0, largement plus eloigne que les 9 autres."""
    salaires = pd.Series([100, 101, 99, 100, 102, 98, 101, 99, 100, 500])
    scores = robust_zscore(salaires)
    score_de_l_outlier = scores.iloc[-1]
    scores_des_autres = scores.iloc[:-1]
    assert abs(score_de_l_outlier) > 5
    assert scores_des_autres.abs().max() < 2


def test_salaires_tous_identiques_ne_plante_pas_et_donne_zero_partout():
    """Cas limite : un groupe ou tout le monde gagne exactement pareil. Il n'y a alors aucune
    dispersion, donc aucune anomalie ne peut etre detectee : la fonction doit renvoyer 0 pour tout
    le monde, sans erreur (division par zero) ni valeur manquante (NaN)."""
    salaires = pd.Series([100, 100, 100, 100, 100])
    scores = robust_zscore(salaires)
    assert (scores == 0).all()
    assert not scores.isna().any()


def test_groupe_presque_homogene_avec_un_seul_ecart_reste_detectable():
    """Ceci est un test de non-regression sur un bug corrige precedemment (voir corrections.txt,
    point 5) : dans un tres petit groupe ou presque tout le monde a le meme salaire, l'ancienne
    version de la fonction renvoyait 0 pour tout le monde meme s'il y avait un veritable ecart,
    car son calcul habituel (base sur la dispersion typique du groupe) ne fonctionne pas quand le
    groupe est trop homogene. La version actuelle doit, dans ce cas precis, retomber sur un autre
    mode de calcul (base sur l'ecart-type) pour rester capable de reperer le salarie qui se
    demarque : son score ne doit donc plus etre 0."""
    salaires = pd.Series([100, 100, 100, 100, 130])
    scores = robust_zscore(salaires)
    assert scores.iloc[-1] != 0
    assert abs(scores.iloc[-1]) > abs(scores.iloc[0])


def test_valeur_texte_illisible_devient_juste_une_absence_de_score():
    """Si une valeur du groupe n'est pas un nombre exploitable (texte, cellule corrompue...), elle
    ne doit ni faire planter le calcul, ni fausser le score des autres salaries : elle doit juste
    obtenir un score manquant (NaN), comme un salaire inconnu."""
    salaires = pd.Series([100, 101, 99, "texte_invalide", 102])
    scores = robust_zscore(salaires)
    assert pd.isna(scores.iloc[3])
    assert not scores.iloc[[0, 1, 2, 4]].isna().any()


def test_ecart_positif_et_ecart_negatif_sont_bien_distingues():
    """Un salarie qui gagne beaucoup MOINS que le groupe doit avoir un score negatif, et un
    salarie qui gagne beaucoup PLUS doit avoir un score positif : le signe du score indique donc
    le sens de l'ecart, pas seulement son ampleur."""
    salaires = pd.Series([100, 100, 100, 100, 100, 40, 300])
    scores = robust_zscore(salaires)
    assert scores.iloc[5] < 0   # 40 : tres en dessous du groupe
    assert scores.iloc[6] > 0   # 300 : tres au-dessus du groupe
