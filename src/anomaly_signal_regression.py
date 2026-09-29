#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Régression du salaire : on entraîne un modèle sur les salariés actuels, puis on vérifie le salaire
d'un nouvel embauché ou d'un salarié dont on revoit le salaire."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from anomaly_pretraitement import preparer_employes

# Ce qu'on connaît d'un nouvel embauché, et d'un salarié déjà dans l'entreprise.
COLONNES_EMBAUCHE = ["Job_Family", "Grade", "Age", "Hot_job"]
COLONNES_SALARIE = ["Job_Family", "Grade", "Anciennete", "Age", "Competence_N1",
                    "Positionnement_9BOX", "Hot_job"]


def construire_X(df: pd.DataFrame, colonnes: list) -> pd.DataFrame:
    # Métier et grade en colonnes 0/1
    return pd.get_dummies(df[colonnes], columns=["Job_Family", "Grade"], dtype=float)


def entrainer(df: pd.DataFrame, colonnes: list):
    X = construire_X(df, colonnes)
    # Log du salaire : l'écart se lit en %, comparable d'un grade à l'autre
    Y = np.log(df["Fixe_Annuel_MAD"])

    modele = LinearRegression().fit(X, Y)
    Y_pred = modele.predict(X)

    metriques = {
        "R2": r2_score(Y, Y_pred),
        "MAE": mean_absolute_error(Y, Y_pred),
        "RMSE": mean_squared_error(Y, Y_pred) ** 0.5,
    }
    reg = {
        "modele": modele,
        "colonnes": colonnes,
        "colonnes_X": list(X.columns),
        "ecart_type": (Y - Y_pred).std(),  # l'erreur normale du modèle
    }
    return reg, metriques


def evaluer(profils: pd.DataFrame, reg: dict, seuil: float = 2.0) -> pd.DataFrame:
    """profils : les colonnes du modèle + le salaire proposé (Fixe_Annuel_MAD)."""
    profils = profils.copy()
    # Mêmes colonnes 0/1 qu'à l'entraînement
    X = construire_X(profils, reg["colonnes"]).reindex(columns=reg["colonnes_X"], fill_value=0)
    log_attendu = reg["modele"].predict(X)

    profils["Salaire_Attendu"] = np.exp(log_attendu)
    profils["Reg_Z"] = (np.log(profils["Fixe_Annuel_MAD"]) - log_attendu) / reg["ecart_type"]
    profils["Reg_Flag"] = profils["Reg_Z"].abs() >= seuil
    return profils


if __name__ == "__main__":
    projet = Path(__file__).resolve().parent.parent
    df = preparer_employes(projet / "input" / "employes.csv",
                           projet / "input" / "bands.csv",
                           projet / "input" / "market.csv")

    # 1. Entraîner les deux modèles sur les salariés actuels et les enregistrer
    dossier = projet / "models"
    dossier.mkdir(exist_ok=True)
    for nom, colonnes in [("embauche", COLONNES_EMBAUCHE), ("salarie", COLONNES_SALARIE)]:
        reg, metriques = entrainer(df, colonnes)
        joblib.dump(reg, dossier / f"regression_{nom}.joblib")
        print(nom, metriques)

    # 2. Nouvel embauché : salaire proposé 150
    reg = joblib.load(dossier / "regression_embauche.joblib")
    nouveau = pd.DataFrame([{"Job_Family": "FINANCE", "Grade": 4, "Age": 30, "Hot_job": 0,
                             "Fixe_Annuel_MAD": 150}])
    print(evaluer(nouveau, reg).to_string(index=False))

    # 3. Salarié existant : nouveau salaire proposé 400 pour le premier salarié du fichier
    reg = joblib.load(dossier / "regression_salarie.joblib")
    revu = df.head(1).assign(Fixe_Annuel_MAD=400)
    print(evaluer(revu, reg)[["Matricule", "Fixe_Annuel_MAD", "Salaire_Attendu", "Reg_Z", "Reg_Flag"]]
          .to_string(index=False))
