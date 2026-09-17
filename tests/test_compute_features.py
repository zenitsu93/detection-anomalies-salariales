# -*- coding: utf-8 -*-
"""
Tests de compute_features() : la fonction qui relie chaque salarie a sa fourchette de salaire
interne (bands) et, si disponible, au marche externe, puis calcule les indicateurs de base :

- CompaRatio        = salaire / milieu de la fourchette (Mid)
- RangePenetration  = position du salaire dans la fourchette (0 = au Min, 1 = au Max)
- MarketRatio       = salaire / mediane du marche

C'est une etape cle : si elle se trompe ou plante, tout le reste de la detection est fausse ou
indisponible.
"""

import numpy as np
import pandas as pd
import pytest

from anomaly_core import compute_features


def employes_simples():
    return pd.DataFrame({
        "Matricule": [1, 2],
        "Job_Family": ["IT", "IT"],
        "Grade": ["G1", "G1"],
        "Fixe_Annuel_MAD": [100000, 120000],
        "Anciennete": [1, 7],
    })


def bands_simples():
    return pd.DataFrame({
        "Job_Family": ["IT"],
        "Grade": ["G1"],
        "Min": [90000],
        "Mid": [110000],
        "Max": [130000],
    })


def test_les_ratios_de_base_sont_calcules_correctement():
    """Verifie, avec des chiffres simples et verifiables a la main, que CompaRatio et
    RangePenetration correspondent bien a leur definition. Salarie 1 : 100 000 dans une fourchette
    90 000-110 000-130 000 -> CompaRatio = 100000/110000, RangePenetration = 10000/40000 = 0.25."""
    resultat = compute_features(employes_simples(), bands_simples(), None)
    assert resultat.loc[0, "CompaRatio"] == pytest.approx(100000 / 110000)
    assert resultat.loc[0, "RangePenetration"] == pytest.approx(0.25)
    assert resultat.loc[1, "CompaRatio"] == pytest.approx(120000 / 110000)
    assert resultat.loc[1, "RangePenetration"] == pytest.approx(0.75)


def test_tranche_d_anciennete_ajoutee_pour_chaque_salarie():
    """Verifie que la colonne Anciennete_Bucket est bien ajoutee et correctement remplie a partir
    de la colonne Anciennete (1 an -> "0-2", 7 ans -> "6-12")."""
    resultat = compute_features(employes_simples(), bands_simples(), None)
    assert list(resultat["Anciennete_Bucket"]) == ["0-2", "6-12"]


def test_sans_fichier_marche_le_ratio_marche_est_vide_partout():
    """Si aucun fichier marche n'est fourni (cas --market absent), MarketRatio doit exister mais
    rester vide (NaN) pour tout le monde, sans faire planter le calcul."""
    resultat = compute_features(employes_simples(), bands_simples(), None)
    assert resultat["MarketRatio"].isna().all()


def test_avec_fichier_marche_le_ratio_marche_est_calcule():
    """Quand un fichier marche est fourni avec une colonne Median, MarketRatio doit valoir
    salaire / mediane marche pour le grade/metier concerne."""
    market = pd.DataFrame({"Job_Family": ["IT"], "Grade": ["G1"], "Median": [115000]})
    resultat = compute_features(employes_simples(), bands_simples(), market)
    assert resultat.loc[0, "MarketRatio"] == pytest.approx(100000 / 115000)


def test_bande_dupliquee_ne_duplique_pas_les_salaries(capsys):
    """Non-regression (corrections.txt, point 1) : si le fichier bands contient deux lignes pour
    le meme couple Job_Family/Grade, chaque salarie concerne ne doit PAS se retrouver duplique
    dans le resultat (une seule ligne bands doit etre gardee), et un message doit prevenir de la
    situation plutot que de la laisser passer en silence."""
    employes = employes_simples()
    bands_dupliquees = pd.DataFrame({
        "Job_Family": ["IT", "IT"],
        "Grade": ["G1", "G1"],
        "Min": [90000, 0],
        "Mid": [110000, 1],
        "Max": [130000, 2],
    })
    resultat = compute_features(employes, bands_dupliquees, None)
    assert len(resultat) == len(employes)  # pas de duplication de salaries
    message_erreurs = capsys.readouterr().err
    assert "dupliqu" in message_erreurs.lower()


def test_salarie_sans_grade_correspondant_reste_visible_mais_sans_ratio(capsys):
    """Si le grade/metier d'un salarie n'existe pas dans bands (faute de frappe, grade retire...),
    ce salarie doit rester dans le resultat (pas disparaitre silencieusement), avec Min/Mid/Max/
    CompaRatio manquants (NaN), et un message doit signaler la situation."""
    employes = pd.concat([
        employes_simples(),
        pd.DataFrame({
            "Matricule": [3], "Job_Family": ["IT"], "Grade": ["GRADE_INCONNU"],
            "Fixe_Annuel_MAD": [100000], "Anciennete": [2],
        }),
    ], ignore_index=True)
    resultat = compute_features(employes, bands_simples(), None)
    assert len(resultat) == 3
    ligne_orpheline = resultat[resultat["Matricule"] == 3].iloc[0]
    assert pd.isna(ligne_orpheline["Mid"])
    assert pd.isna(ligne_orpheline["CompaRatio"])
    message_erreurs = capsys.readouterr().err
    assert "sans correspondance" in message_erreurs.lower()


def test_un_mid_a_zero_dans_bands_ne_fait_pas_planter_ni_donner_l_infini():
    """Non-regression (corrections.txt, point 9) : un Mid a 0 dans bands (donnee mal saisie) ne
    doit pas produire une valeur infinie pour CompaRatio (ce qui ferait planter le calcul
    d'intelligence artificielle plus loin), mais une valeur manquante (NaN), traitee comme un
    salaire sans reference fiable."""
    bands_avec_zero = bands_simples().copy()
    bands_avec_zero["Mid"] = 0
    resultat = compute_features(employes_simples(), bands_avec_zero, None)
    assert resultat["CompaRatio"].isna().all()
    assert not np.isinf(resultat["CompaRatio"]).any()


def test_un_market_median_a_zero_ne_fait_pas_planter_ni_donner_l_infini():
    """Meme verification que le test precedent, mais pour Market_Median a 0 dans le fichier
    marche (protection ajoutee en meme temps, meme cause possible)."""
    market_avec_zero = pd.DataFrame({"Job_Family": ["IT"], "Grade": ["G1"], "Median": [0]})
    resultat = compute_features(employes_simples(), bands_simples(), market_avec_zero)
    assert resultat["MarketRatio"].isna().all()
    assert not np.isinf(resultat["MarketRatio"]).any()


def test_salaire_ecrit_en_texte_devient_une_valeur_manquante_plutot_que_de_planter(capsys):
    """Si une valeur de salaire n'est pas un nombre exploitable (texte parasite, cellule
    corrompue...), l'employe concerne doit avoir un salaire manquant (NaN) plutot que de faire
    planter tout le traitement pour tout le monde, avec un message d'avertissement."""
    employes = employes_simples()
    employes["Fixe_Annuel_MAD"] = employes["Fixe_Annuel_MAD"].astype(object)
    employes.loc[0, "Fixe_Annuel_MAD"] = "N/A"
    resultat = compute_features(employes, bands_simples(), None)
    assert pd.isna(resultat.loc[0, "CompaRatio"])
    assert resultat.loc[1, "CompaRatio"] == pytest.approx(120000 / 110000)  # l'autre salarie est intact
    message_erreurs = capsys.readouterr().err
    assert "non numérique" in message_erreurs or "non numerique" in message_erreurs.lower()


def test_ni_job_family_ni_grade_en_commun_leve_une_erreur_claire():
    """S'il n'y a aucune colonne commune (Job_Family ou Grade) entre le fichier employes et le
    fichier bands, la jointure est impossible : la fonction doit le signaler immediatement par une
    erreur explicite plutot que de produire un resultat vide ou incoherent."""
    employes = pd.DataFrame({"Matricule": [1], "Fixe_Annuel_MAD": [100000]})
    bands = pd.DataFrame({"Min": [90000], "Mid": [110000], "Max": [130000]})
    with pytest.raises(KeyError):
        compute_features(employes, bands, None)


def test_bands_sans_colonne_max_leve_une_erreur_explicite_des_le_depart():
    """Non-regression : si le fichier bands ne contient pas toutes les colonnes necessaires (ici
    Max manquant), l'erreur doit etre immediate et explicite ("colonnes manquantes"), plutot que
    de planter plus loin dans le calcul avec un message technique incomprehensible pour un
    utilisateur non developpeur."""
    bands_incompletes = bands_simples().drop(columns=["Max"])
    with pytest.raises(KeyError, match="Colonnes manquantes"):
        compute_features(employes_simples(), bands_incompletes, None)
