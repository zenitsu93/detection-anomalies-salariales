# -*- coding: utf-8 -*-
"""
Tests de aggregate_risk() : la fonction qui combine le score des regles simples (Rule_Score) et le
score de l'intelligence artificielle (ML_AnomalyScore) en un seul score de risque global
(RiskScore), puis traduit ce score en niveau de priorite (Critical / Major / Minor / Info).

Par defaut, les regles simples comptent pour 70% du score final et l'IA pour 30%.
"""

import pandas as pd
import pytest

from anomaly_core import aggregate_risk


def df_avec(rule_score, ml_score):
    return pd.DataFrame({"Rule_Score": [rule_score], "ML_AnomalyScore": [ml_score]})


def test_score_de_risque_est_bien_la_moyenne_ponderee_par_defaut():
    """Avec les poids par defaut (70% regles, 30% IA), un Rule_Score de 40 et un ML_AnomalyScore
    de 80 doivent donner un RiskScore de 0.7*40 + 0.3*80 = 52."""
    resultat = aggregate_risk(df_avec(rule_score=40, ml_score=80), rule_params={})
    assert resultat.loc[0, "RiskScore"] == pytest.approx(52)


@pytest.mark.parametrize(
    "score, priorite_attendue",
    [
        (100, "Critical"),
        (70, "Critical"),   # borne basse de Critical : incluse
        (69.9, "Major"),
        (50, "Major"),      # borne basse de Major : incluse
        (49.9, "Minor"),
        (30, "Minor"),      # borne basse de Minor : incluse
        (29.9, "Info"),
        (0, "Info"),
    ],
)
def test_chaque_niveau_de_priorite_correspond_au_bon_intervalle_de_score(score, priorite_attendue):
    """Verifie, y compris exactement aux frontieres entre deux niveaux, que le score de risque est
    bien traduit dans le bon niveau de priorite (Critical/Major/Minor/Info). Une erreur de
    frontiere ferait passer un cas grave inapercu, ou inversement remonterait des cas sans gravite."""
    df = pd.DataFrame({"Rule_Score": [score], "ML_AnomalyScore": [0]})
    resultat = aggregate_risk(df, rule_params={"rule_weight": 1.0, "ml_weight": 0.0})
    assert resultat.loc[0, "Severity"] == priorite_attendue


def test_ponderation_personnalisee_du_rulebook_est_respectee():
    """Si le rulebook demande de donner tout le poids a l'IA (ml_weight=1) et aucun aux regles
    (rule_weight=0), le score de risque final doit alors correspondre exactement au score IA,
    quel que soit le score des regles simples."""
    resultat = aggregate_risk(
        df_avec(rule_score=999, ml_score=42), rule_params={"rule_weight": 0.0, "ml_weight": 1.0}
    )
    assert resultat.loc[0, "RiskScore"] == pytest.approx(42)


def test_seuils_de_priorite_personnalises_sont_pris_en_compte():
    """Si le rulebook redefinit les intervalles de priorite, ce sont ces intervalles personnalises
    qui doivent etre utilises pour classer chaque salarie, pas les seuils par defaut."""
    buckets_personnalises = {"Critical": [90, 100], "Major": [0, 89]}
    resultat = aggregate_risk(
        df_avec(rule_score=80, ml_score=0),
        rule_params={"rule_weight": 1.0, "ml_weight": 0.0, "prioritization_buckets": buckets_personnalises},
    )
    # 80 tomberait en "Critical" avec les seuils par defaut (>=70), mais doit tomber en "Major"
    # avec les seuils personnalises ci-dessus (Critical ne commence qu'a partir de 90).
    assert resultat.loc[0, "Severity"] == "Major"


def test_score_manquant_est_traite_comme_zero_sans_planter():
    """Si, pour une raison quelconque, Rule_Score ou ML_AnomalyScore est manquant (NaN) pour un
    salarie, le calcul ne doit pas planter ni produire un score manquant : la valeur manquante
    doit etre traitee comme un 0."""
    df = pd.DataFrame({"Rule_Score": [float("nan")], "ML_AnomalyScore": [50]})
    resultat = aggregate_risk(df, rule_params={})
    assert resultat.loc[0, "RiskScore"] == pytest.approx(0.3 * 50)
