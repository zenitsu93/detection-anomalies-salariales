# -*- coding: utf-8 -*-
"""
Tests de ml_anomaly() : la fonction qui fait appel a un programme d'intelligence artificielle
(un "IsolationForest") pour reperer des profils qui se demarquent, non pas sur un seul critere,
mais sur une combinaison de plusieurs (salaire, ratios, age, anciennete...).

On ne cherche pas ici a tester l'intelligence artificielle elle-meme (c'est une brique standard et
deja largement testee par ailleurs), mais a verifier que notre fonction :
- lui fournit des donnees dans un format correct et sans planter,
- lui transmet bien les reglages du rulebook (contamination, nombre d'arbres),
- renvoie bien un score exploitable (compris entre 0 et 100).
"""

import numpy as np
import pandas as pd
import pytest

import anomaly_core
from anomaly_core import ml_anomaly


def jeu_de_donnees(n=30):
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "Fixe_Annuel_MAD": rng.normal(100000, 5000, n),
        "CompaRatio": rng.normal(1.0, 0.05, n),
        "RangePenetration": rng.normal(0.5, 0.1, n),
        "MarketRatio": rng.normal(1.0, 0.05, n),
        "Age": rng.normal(40, 8, n),
        "Anciennete": rng.normal(8, 3, n),
    })


def test_le_score_renvoye_est_toujours_compris_entre_0_et_100():
    """Quel que soit le contenu du fichier, le score d'anomalie doit toujours etre ramene sur une
    echelle comparable de 0 a 100, pour pouvoir etre combine avec le score des regles simples."""
    df = jeu_de_donnees()
    resultat = ml_anomaly(df, rule_params={})
    assert resultat["ML_AnomalyScore"].between(0, 100).all()


def test_un_profil_tres_atypique_obtient_un_score_plus_eleve_que_la_moyenne():
    """Un salarie dont TOUTES les caracteristiques sont tres inhabituelles par rapport au reste du
    fichier (salaire, ratios, age, anciennete) doit obtenir un score d'anomalie nettement plus
    eleve que la moyenne des salaries "ordinaires"."""
    df = jeu_de_donnees()
    profil_atypique = pd.DataFrame({
        "Fixe_Annuel_MAD": [500000], "CompaRatio": [2.5], "RangePenetration": [2.0],
        "MarketRatio": [3.0], "Age": [22], "Anciennete": [30],
    })
    df = pd.concat([df, profil_atypique], ignore_index=True)
    resultat = ml_anomaly(df, rule_params={})
    score_profil_atypique = resultat["ML_AnomalyScore"].iloc[-1]
    score_moyen_des_autres = resultat["ML_AnomalyScore"].iloc[:-1].mean()
    assert score_profil_atypique > score_moyen_des_autres


def test_colonne_totalement_vide_est_ignoree_sans_planter():
    """Si une colonne habituellement utilisee est entierement vide (ex: MarketRatio quand aucun
    fichier marche n'a ete fourni), elle ne doit pas faire planter le calcul : elle est
    simplement ecartee des variables analysees par l'intelligence artificielle."""
    df = jeu_de_donnees()
    df["MarketRatio"] = np.nan
    resultat = ml_anomaly(df, rule_params={})
    assert resultat["ML_AnomalyScore"].notna().all()


def test_les_champs_rh_optionnels_sont_pris_en_compte_s_ils_sont_presents():
    """Quand les colonnes RH supplementaires (niveau de competence, positionnement 9Box, hot job)
    sont presentes dans le fichier, la fonction doit les utiliser sans planter."""
    df = jeu_de_donnees()
    df["Competence_N1"] = np.random.default_rng(1).integers(1, 5, len(df))
    df["Positionnement_9BOX"] = np.random.default_rng(2).integers(1, 9, len(df))
    df["Hot_job"] = np.random.default_rng(3).integers(0, 2, len(df))
    resultat = ml_anomaly(df, rule_params={})
    assert resultat["ML_AnomalyScore"].between(0, 100).all()


class _FausseForet:
    """Remplace le veritable IsolationForest le temps d'un test : elle ne fait aucun vrai calcul,
    elle se contente de retenir avec quels reglages elle a ete appelee. Cela permet de verifier
    que ml_anomaly() transmet bien les reglages du rulebook, sans dependre du resultat statistique
    (potentiellement variable) d'une veritable foret aleatoire."""

    reglages_recus = {}

    def __init__(self, **kwargs):
        _FausseForet.reglages_recus = kwargs

    def fit(self, X):
        self._n = X.shape[0]
        return self

    def score_samples(self, X):
        return np.zeros(X.shape[0])


def test_contamination_et_nombre_d_arbres_sont_bien_transmis_depuis_le_rulebook(monkeypatch):
    """Non-regression (corrections.txt, point 10) : ml_contamination et ml_n_estimators etaient
    auparavant fixes en dur dans le code (0.05 / 200). Ce test verifie, sans dependre du resultat
    statistique, que les valeurs fournies dans le rulebook sont bien celles effectivement
    transmises au modele - la preuve que ce reglage n'est plus fige dans le code."""
    monkeypatch.setattr(anomaly_core, "IsolationForest", _FausseForet)
    df = jeu_de_donnees(n=10)
    ml_anomaly(df, rule_params={"ml_contamination": 0.2, "ml_n_estimators": 7})
    assert _FausseForet.reglages_recus["contamination"] == pytest.approx(0.2)
    assert _FausseForet.reglages_recus["n_estimators"] == 7


def test_sans_reglage_dans_le_rulebook_les_valeurs_par_defaut_sont_inchangees(monkeypatch):
    """Si le rulebook ne precise rien, les valeurs utilisees doivent rester celles d'origine
    (0.05 de contamination, 200 arbres), pour ne changer aucun resultat existant chez les clients
    qui n'ont pas mis a jour leur rulebook."""
    monkeypatch.setattr(anomaly_core, "IsolationForest", _FausseForet)
    df = jeu_de_donnees(n=10)
    ml_anomaly(df, rule_params={})
    assert _FausseForet.reglages_recus["contamination"] == pytest.approx(0.05)
    assert _FausseForet.reglages_recus["n_estimators"] == 200
