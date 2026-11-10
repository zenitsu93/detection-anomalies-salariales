#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Régression du salaire : le modèle apprend sur 80 % des salariés, il est vérifié sur les 20 %
restants, puis il prédit un salaire avec une fourchette.

Ce qu'il ne lit pas, et pourquoi :
- le salaire lui-même : c'est ce qu'il doit deviner. Le lui donner, ce serait lui donner la réponse ;
- le Min et le Max de la grille : ils se déduisent du Mid, ils ne diraient rien de plus ;
- la médiane du marché seule : avec le Mid et le ratio grille / marché, elle est déjà connue ;
- le sexe : le modèle apprendrait l'écart de salaire entre femmes et hommes et le recopierait ;
- le pôle : deux salariés du même métier et du même niveau ne doivent pas être payés différemment parce
  qu'ils sont dans deux pôles différents.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from anomaly_pretraitement import preparer_employes

# Le tableau unique des colonnes que lit le modèle, avec leur type. Pour en retirer une, effacer sa
# ligne ; pour en ajouter une, ajouter une ligne.
# - « catégorie » : chaque valeur a son propre effet (colonnes 0/1). Le 9-Box l'est même s'il est écrit
#   avec des chiffres : ses cases ne sont pas rangées de la moins bonne à la meilleure.
# - « nombre » : un seul effet, « tant de % de salaire en plus par unité en plus ».
COLONNES = {
    "Job_Family": "catégorie",           # le métier
    "Niveau": "catégorie",               # le niveau (1 à 7)
    "Mid": "nombre",                     # le milieu de la grille du métier + niveau
    "Ratio_Grille_Marche": "nombre",     # Mid / médiane du marché : 1,10 = la grille paie 10 % de plus
    "Anciennete": "nombre",              # en années
    "Age": "nombre",                     # en années
    "Competence_N1": "nombre",           # la note de compétence de l'an dernier
    "Performance_N1": "catégorie",       # la performance de l'an dernier (« A l'objectif »...)
    "Positionnement_9BOX": "catégorie",  # la case 9-Box
    "Hot_job": "nombre",                 # la tension du métier sur le marché (0 à 2)
    "Rang_Etude_Max": "nombre",          # le niveau d'études : 0 = secondaire, 1 = BAC... 7 = BAC+7
    "Cat_Ecole_Max": "catégorie",        # la catégorie d'école (ingénieur, commerce, université, autres)
}
# Pourquoi le niveau d'études en nombre (son rang) : certains niveaux comptent très peu de salariés
# (BAC+6, expertise comptable), le modèle ne pourrait rien apprendre sur eux seuls ; avec le rang, il
# apprend un seul effet, qui vaut pour tous les niveaux.


def tableau_x(df: pd.DataFrame, colonnes) -> pd.DataFrame:
    """Le tableau que lit le modèle : les colonnes demandées, les catégories en colonnes 0/1.
    - Le Mid est lu en logarithme, comme le salaire : « 10 % de Mid en plus » donne alors le même effet
      en % à tous les niveaux.
    - Une catégorie vide devient « Inconnu », qui a sa propre colonne 0/1. Une colonne de texte absente
      de COLONNES (la compétence, si elle est écrite en libellés) est elle aussi lue en catégorie.
    - Un niveau d'études inconnu : rang mis à 0, et une colonne « Rang_Etude_Inconnu » à 1, qui reçoit
      son propre effet (sinon il compterait comme « secondaire »).
    - Une autre case vide parmi les nombres reste vide : ce salarié n'apprend pas au modèle et n'a pas
      de salaire prédit."""
    x = df[list(colonnes)].copy()
    if "Mid" in x:
        x["Mid"] = np.log(x["Mid"].where(x["Mid"] > 0))
    if "Rang_Etude_Max" in x:
        rang = pd.to_numeric(x["Rang_Etude_Max"], errors="coerce")
        x["Rang_Etude_Inconnu"] = rang.isna().astype(float)
        x["Rang_Etude_Max"] = rang.fillna(0)
    categories = [c for c in colonnes if COLONNES.get(c) == "catégorie" or not pd.api.types.is_numeric_dtype(x[c])]
    for colonne in categories:
        x[colonne] = x[colonne].astype(object).where(x[colonne].notna(), "Inconnu").astype(str)
    return pd.get_dummies(x, columns=categories, dtype=float)


def entrainer(df: pd.DataFrame, colonnes=None):
    """Entraîne le modèle. colonnes : ce que lit le modèle ; sans précision, celles de COLONNES que le
    tableau a, avec au moins une case remplie (une colonne absente du fichier est laissée de côté).
    analyse_diplomes/diplome.py en donne d'autres, pour comparer le modèle sans et avec le diplôme."""
    if colonnes is None:
        colonnes = [c for c in COLONNES if c in df and df[c].notna().any()]
    df = df[pd.to_numeric(df["Fixe_Annuel_MAD"], errors="coerce") > 0]
    X = tableau_x(df, colonnes)
    # Un salarié avec une case vide parmi les nombres (pas de grille, âge manquant...) est laissé de côté.
    X = X[X.notna().all(axis=1)]
    # Log du salaire : l'écart se lit en %, comparable d'un niveau à l'autre
    Y = np.log(df.loc[X.index, "Fixe_Annuel_MAD"].astype(float))

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
    """profils : les colonnes du modèle. Un profil avec une case vide parmi les nombres n'a pas de
    salaire prédit (cases vides)."""
    profils = profils.copy()
    # Mêmes colonnes 0/1 qu'à l'entraînement. Une valeur jamais vue à l'entraînement (un nouveau
    # métier...) n'a pas de colonne : elle compte comme la valeur de référence.
    X = tableau_x(profils, reg["colonnes"]).reindex(columns=reg["colonnes_X"], fill_value=0)
    complet = X.notna().all(axis=1).to_numpy()
    log_predit = np.full(len(X), np.nan)
    if complet.any():
        log_predit[complet] = reg["modele"].predict(X[complet])
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
    print("Colonnes lues :", ", ".join(reg["colonnes"]))
    print(metriques)

    # 2. Salaire prédit et sa fourchette pour le premier salarié du fichier
    reg = joblib.load(dossier / "regression.joblib")
    revu = df.head(1)
    print(predire(revu, reg)[["Matricule", "Fixe_Annuel_MAD", "Salaire_Predit", "Fourchette_Basse",
                              "Fourchette_Haute"]].round(1).to_string(index=False))
