#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Régression du salaire : le modèle apprend sur 80 % des salariés, il est vérifié sur les 20 %
restants, puis il prédit un salaire avec une fourchette, pour un salarié dont on revoit le
salaire."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from anomaly_pretraitement import preparer_employes

# Ce qu'on connaît d'un salarié déjà dans l'entreprise.
COLONNES = ["Job_Family", "Niveau", "Anciennete", "Age", "Competence_N1", "Positionnement_9BOX",
            "Hot_job"]
# Les colonnes du diplôme qu'on peut donner en plus au modèle (voir tableau_x). Le modèle de l'aide à
# la décision ne les lit pas ; analyse_diplomes/diplome.py les essaie, pour voir si elles rendent le
# salaire prédit plus juste.
COLONNES_DIPLOME = ["Tranche_Etude", "Cat_Ecole_Max"]
# Les colonnes qui sont des catégories et pas des nombres : chacune devient des colonnes 0/1.
CATEGORIES = ["Job_Family", "Niveau", *COLONNES_DIPLOME]


def tableau_x(df: pd.DataFrame, colonnes: list) -> pd.DataFrame:
    """Le tableau que lit le modèle : les colonnes demandées, les catégories en colonnes 0/1.
    Pourquoi un diplôme inconnu devient « Inconnu » : le modèle refuse les cases vides. « Inconnu » a
    alors sa propre colonne 0/1, au lieu de recevoir un diplôme inventé."""
    x = df[colonnes].copy()
    for colonne in COLONNES_DIPLOME:
        if colonne in colonnes:
            x[colonne] = x[colonne].fillna("Inconnu")
    return pd.get_dummies(x, columns=[c for c in CATEGORIES if c in colonnes], dtype=float)


def entrainer(df: pd.DataFrame, colonnes: list = COLONNES):
    # colonnes : ce que lit le modèle ; sans précision, COLONNES. Pourquoi pouvoir en donner d'autres :
    # analyse_diplomes/diplome.py compare le modèle sans et avec le diplôme.
    # Métier et niveau (et le diplôme, s'il est demandé) en colonnes 0/1
    X = tableau_x(df, colonnes)
    # Log du salaire : l'écart se lit en %, comparable d'un niveau à l'autre
    Y = np.log(df["Fixe_Annuel_MAD"])

    # 20 % des salariés mis de côté : le modèle ne les voit pas en apprenant, on vérifie sur eux
    # s'il devine juste. random_state=42 : le même tirage à chaque lancement
    X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size=0.2, random_state=42)

    modele = LinearRegression().fit(X_train, Y_train)
    Y_pred = modele.predict(X_test)

    # MAE et RMSE en kMAD (on repasse du log au salaire) : « en moyenne, la prédiction se trompe
    # de tant de kMAD »
    metriques = {
        "R2": r2_score(Y_test, Y_pred),
        "MAE": mean_absolute_error(np.exp(Y_test), np.exp(Y_pred)),
        "RMSE": mean_squared_error(np.exp(Y_test), np.exp(Y_pred)) ** 0.5,
    }
    # Fourchette : on range les erreurs des salariés mis de côté du plus bas au plus haut, et on
    # retire les 5 % les plus basses et les 5 % les plus hautes : 9 fois sur 10, le vrai salaire
    # tombe dedans
    bas, haut = np.quantile(Y_test - Y_pred, [0.05, 0.95])
    reg = {
        "modele": modele,
        # Pourquoi garder la liste des colonnes lues : predire doit refaire exactement le même tableau.
        "colonnes": list(colonnes),
        "colonnes_X": list(X.columns),
        "fourchette": (bas, haut),
    }
    return reg, metriques


def predire(profils: pd.DataFrame, reg: dict) -> pd.DataFrame:
    """profils : les colonnes du modèle."""
    profils = profils.copy()
    # Mêmes colonnes 0/1 qu'à l'entraînement. Un modèle enregistré avant que la liste « colonnes » soit
    # gardée avec lui lisait COLONNES.
    X = tableau_x(profils, reg.get("colonnes", COLONNES)).reindex(columns=reg["colonnes_X"], fill_value=0)
    log_predit = reg["modele"].predict(X)
    bas, haut = reg["fourchette"]

    profils["Salaire_Predit"] = np.exp(log_predit)
    profils["Fourchette_Basse"] = np.exp(log_predit + bas)
    profils["Fourchette_Haute"] = np.exp(log_predit + haut)
    return profils


if __name__ == "__main__":
    projet = Path(__file__).resolve().parent.parent
    df = preparer_employes(projet / "input" / "employes.xlsx",
                           projet / "input" / "bands.xlsx",
                           projet / "input" / "market.xlsx")

    # 1. Entraîner le modèle et l'enregistrer
    dossier = projet / "models"
    dossier.mkdir(exist_ok=True)
    reg, metriques = entrainer(df)
    joblib.dump(reg, dossier / "regression.joblib")
    print(metriques)

    # 2. Salaire prédit et sa fourchette pour le premier salarié du fichier
    reg = joblib.load(dossier / "regression.joblib")
    revu = df.head(1)
    print(predire(revu, reg)[["Matricule", "Fixe_Annuel_MAD", "Salaire_Predit", "Fourchette_Basse",
                              "Fourchette_Haute"]].round(1).to_string(index=False))
