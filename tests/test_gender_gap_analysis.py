# -*- coding: utf-8 -*-
"""
Tests de gender_gap_analysis() : la fonction (optionnelle) qui calcule, pour chaque
metier/grade, le salaire median des hommes et des femmes, et le ratio entre les deux
(M_div_F > 1 signifie que les hommes gagnent, en median, plus que les femmes sur ce
metier/grade).
"""

import numpy as np
import pandas as pd
import pytest

from anomaly_core import gender_gap_analysis


def test_medianes_et_ratio_calcules_correctement_sur_un_cas_simple():
    """Avec 2 femmes (100 000 et 120 000, mediane 110 000) et 2 hommes (140 000 et 160 000,
    mediane 150 000) sur le meme metier/grade, le ratio M_div_F doit valoir 150000/110000."""
    df = pd.DataFrame({
        "Job_Family": ["IT"] * 4,
        "Grade": ["G1"] * 4,
        "Sexe": ["F", "F", "M", "M"],
        "Fixe_Annuel_MAD": [100000, 120000, 140000, 160000],
    })
    resultat = gender_gap_analysis(df)
    ligne = resultat.iloc[0]
    assert ligne["Median_F"] == pytest.approx(110000)
    assert ligne["Median_M"] == pytest.approx(150000)
    assert ligne["M_div_F"] == pytest.approx(150000 / 110000)


def test_colonne_sexe_absente_leve_une_erreur_explicite():
    """Sans colonne Sexe dans le fichier, l'analyse est impossible : la fonction doit le signaler
    clairement par une erreur plutot que de produire un resultat vide ou incoherent."""
    df = pd.DataFrame({"Job_Family": ["IT"], "Fixe_Annuel_MAD": [100000]})
    with pytest.raises(ValueError):
        gender_gap_analysis(df)


def test_un_seul_sexe_present_donne_un_ratio_manquant_sans_planter():
    """Si un metier/grade ne compte que des femmes (ou que des hommes), le ratio M_div_F n'a pas
    de sens et doit rester manquant (NaN), sans faire planter le calcul pour autant."""
    df = pd.DataFrame({
        "Job_Family": ["IT", "IT"],
        "Grade": ["G1", "G1"],
        "Sexe": ["F", "F"],
        "Fixe_Annuel_MAD": [100000, 120000],
    })
    resultat = gender_gap_analysis(df)
    assert pd.isna(resultat.iloc[0]["M_div_F"])


def test_codes_de_sexe_inattendus_declenchent_un_avertissement(capsys):
    """Non-regression (corrections.txt, point 11) : si la colonne Sexe contient autre chose que
    exactement "M" et "F" (ici "Autre"), un avertissement doit etre affiche pour que l'absence
    eventuelle du ratio ne passe pas inapercue - alors qu'avant cette correction, rien ne
    signalait la situation."""
    df = pd.DataFrame({
        "Job_Family": ["IT", "IT", "IT"],
        "Grade": ["G1", "G1", "G1"],
        "Sexe": ["F", "M", "Autre"],
        "Fixe_Annuel_MAD": [100000, 140000, 130000],
    })
    gender_gap_analysis(df)
    message_erreurs = capsys.readouterr().err
    assert "Sexe" in message_erreurs
    assert "Autre" in message_erreurs


def test_codes_de_sexe_valides_ne_declenchent_aucun_avertissement(capsys):
    """A l'inverse, si la colonne Sexe ne contient que des "M" et des "F", aucun avertissement ne
    doit apparaitre : l'outil ne doit pas crier au loup sur des donnees parfaitement normales."""
    df = pd.DataFrame({
        "Job_Family": ["IT", "IT"],
        "Grade": ["G1", "G1"],
        "Sexe": ["F", "M"],
        "Fixe_Annuel_MAD": [100000, 140000],
    })
    gender_gap_analysis(df)
    message_erreurs = capsys.readouterr().err
    assert message_erreurs == ""
