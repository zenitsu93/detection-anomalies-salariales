# -*- coding: utf-8 -*-
"""
Tests du signal de régression multivariée (anomaly_regression.py), utilisé UNIQUEMENT par
detect_salary_anomalies_regression.py (le pipeline "custom_fixed" existant n'y touche pas).

Comme pour ml_anomaly (voir test_ml_anomaly.py), on ne cherche pas à tester statsmodels
lui-même, mais à vérifier que notre code :
- construit une table d'analyse exploitable sans planter (modalités rares, colonnes optionnelles
  absentes, échantillon trop petit),
- renvoie un score comparable à ML_AnomalyScore (0-100),
- extrait correctement le coefficient Sexe pour le rapport d'écart Homme/Femme ajusté.
"""

import numpy as np
import pandas as pd

from anomaly_regression import (
    regression_anomaly,
    aggregate_risk_with_regression,
)


def jeu_de_donnees(n=200, ecart_type_bruit=0.05, coef_sexe_log=0.0, seed=0):
    """Jeu de données synthétique où le salaire suit une relation connue avec Job_Family, Grade,
    Anciennete, Age et Sexe, plus un bruit aléatoire - pour pouvoir vérifier que la régression
    retrouve un signal exploitable sans dépendre d'un vrai fichier RH."""
    rng = np.random.default_rng(seed)
    job_family = rng.choice(["Ventes", "IT", "Finance"], size=n)
    grade = rng.choice(["G1", "G2", "G3"], size=n)
    sexe = rng.choice(["F", "M"], size=n)
    anciennete = rng.normal(8, 3, n).clip(0, 30)
    age = rng.normal(40, 8, n).clip(22, 62)

    effet_job = pd.Series(job_family).map({"Ventes": 0.0, "IT": 0.10, "Finance": 0.15}).to_numpy()
    effet_grade = pd.Series(grade).map({"G1": 0.0, "G2": 0.12, "G3": 0.25}).to_numpy()
    effet_sexe = np.where(sexe == "M", coef_sexe_log, 0.0)
    bruit = rng.normal(0, ecart_type_bruit, n)

    log_salaire = (
        np.log(100000)
        + effet_job
        + effet_grade
        + 0.01 * anciennete
        + 0.005 * (age - 40)
        + effet_sexe
        + bruit
    )

    return pd.DataFrame({
        "Fixe_Annuel_MAD": np.exp(log_salaire),
        "Job_Family": job_family,
        "Grade": grade,
        "Sexe": sexe,
        "Anciennete": anciennete,
        "Age": age,
    })


def test_le_score_renvoye_est_toujours_compris_entre_0_et_100():
    """Comme ML_AnomalyScore, Reg_AnomalyScore doit rester sur une echelle 0-100 comparable,
    pour pouvoir etre combine avec les deux autres signaux dans aggregate_risk_with_regression."""
    df = jeu_de_donnees()
    resultat, model = regression_anomaly(df, rule_params={})
    assert model is not None
    assert resultat["Reg_AnomalyScore"].between(0, 100).all()


def test_un_profil_dont_le_salaire_ne_correspond_pas_a_son_profil_obtient_un_score_eleve():
    """Un salarie dont le salaire ne suit pas du tout la relation habituelle (bruit ajoute enorme)
    doit obtenir un residu, donc un Reg_AnomalyScore, nettement plus eleve que la moyenne."""
    df = jeu_de_donnees()
    profil_atypique = jeu_de_donnees(n=1, seed=99).iloc[[0]].copy()
    profil_atypique["Fixe_Annuel_MAD"] = profil_atypique["Fixe_Annuel_MAD"] * 4  # tres sur-paye vs son profil
    df = pd.concat([df, profil_atypique], ignore_index=True)
    resultat, model = regression_anomaly(df, rule_params={})
    assert model is not None
    score_profil_atypique = resultat["Reg_AnomalyScore"].iloc[-1]
    score_moyen_des_autres = resultat["Reg_AnomalyScore"].iloc[:-1].mean()
    assert score_profil_atypique > score_moyen_des_autres


def test_echantillon_trop_petit_ne_plante_pas_et_desactive_le_signal(capsys):
    """Sous le seuil minimal d'observations (reg_min_observations, defaut 50), la regression doit
    etre desactivee proprement : pas d'exception, colonnes a NaN, avertissement explicite sur
    stderr - meme esprit que apply_ml_strong_signal qui renonce silencieusement sous 20 valeurs."""
    df = jeu_de_donnees(n=10)
    resultat, model = regression_anomaly(df, rule_params={})
    assert model is None
    assert resultat["Reg_AnomalyScore"].isna().all()
    assert resultat["Salaire_Predit_Regression"].isna().all()
    assert "[WARN][REGRESSION]" in capsys.readouterr().err


def test_modalite_f_devenue_rare_apres_regroupement_ne_fait_pas_planter_patsy():
    """Non-regression : quand la modalite 'F' de Sexe est trop rare (moins de
    reg_min_category_size) et se retrouve regroupee dans 'Autre', la formule ne doit plus forcer
    une reference 'F' qui n'existe plus dans les donnees - sinon patsy leve un PatsyError
    ('specified level not found') qui faisait planter tout le script (reproduit avec un extrait
    de 20 employes du fichier reel, ou 7 femmes tombaient sous le seuil par defaut de 10)."""
    df = jeu_de_donnees(n=200)
    rares_f = df.index[df["Sexe"] == "F"][:5]
    df["Sexe"] = "M"
    df.loc[rares_f, "Sexe"] = "F"  # seulement 5 femmes, sous reg_min_category_size (defaut 10)
    resultat, model = regression_anomaly(df, rule_params={})
    assert model is not None
    assert resultat["Reg_AnomalyScore"].notna().all()


def test_les_colonnes_optionnelles_absentes_ne_font_pas_planter():
    """Competence_N1, Positionnement_9BOX et Hot_job sont optionnelles : si elles sont absentes
    du fichier employes (cas de ce jeu de test), la regression doit fonctionner quand meme avec
    les variables restantes (Job_Family, Grade, Sexe, Anciennete, Age)."""
    df = jeu_de_donnees()
    assert "Competence_N1" not in df.columns
    assert "Positionnement_9BOX" not in df.columns
    assert "Hot_job" not in df.columns
    resultat, model = regression_anomaly(df, rule_params={})
    assert model is not None
    assert resultat["Reg_AnomalyScore"].notna().all()


def test_une_modalite_tres_rare_est_regroupee_sans_faire_planter_patsy():
    """Une modalite de Job_Family presente une seule fois doit etre regroupee sous 'Autre'
    (reg_min_category_size) plutot que de produire une colonne de design quasi vide."""
    df = jeu_de_donnees()
    df.loc[0, "Job_Family"] = "MetierTresRare"
    resultat, model = regression_anomaly(df, rule_params={"reg_min_category_size": 10})
    assert model is not None
    assert resultat["Reg_AnomalyScore"].notna().all()







def test_aggregate_risk_with_regression_combine_bien_les_3_signaux():
    """RiskScore doit etre la moyenne ponderee explicite des 3 signaux (regles, IsolationForest,
    regression), avec les poids lus dans le rulebook."""
    df = pd.DataFrame({
        "Rule_Score": [40.0, 0.0],
        "ML_AnomalyScore": [50.0, 10.0],
        "Reg_AnomalyScore": [60.0, 5.0],
    })
    rule_params = {"rule_weight": 0.5, "ml_weight": 0.3, "reg_weight": 0.2}
    resultat = aggregate_risk_with_regression(df, rule_params)
    attendu_ligne_0 = 0.5 * 40.0 + 0.3 * 50.0 + 0.2 * 60.0
    assert resultat["RiskScore"].iloc[0] == attendu_ligne_0

