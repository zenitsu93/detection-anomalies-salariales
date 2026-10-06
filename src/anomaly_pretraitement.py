#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PRÉTRAITEMENT : PRÉPARER LE TABLEAU DES SALARIÉS
================================================

Ce fichier lit les trois fichiers d'entrée (salariés, grille interne « bands », marché) et rend le
DataFrame des salariés prétraité : une ligne par salarié, avec sa fourchette de grille, la médiane
du marché et ses ratios. C'est le DataFrame sur lequel l'analyse va travailler.

C'est la première étape : il n'a besoin d'aucun autre fichier du projet. Le DataFrame qu'il rend est
l'entrée d'anomaly_cohortes.py, dont la sortie est à son tour l'entrée d'anomaly_regles.py, puis
d'anomaly_signal_iforest.py, puis d'anomaly_signal_regression.py.

Utilisation :
- depuis Python :
      from anomaly_pretraitement import preparer_employes
      df = preparer_employes("input/employes.xlsx", "input/bands.xlsx", "input/market.xlsx")
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_pretraitement.py
  Le DataFrame est enregistré dans output/pretraitement/employes_pretraites.xlsx, à ouvrir avec Excel.
"""

from pathlib import Path

import numpy as np
import pandas as pd


def bucket_anciennete(x: object) -> str:
    """Range l'ancienneté (en années) dans une tranche : 0-2, 3-5, 6-12, 13-20 ou >20.
    Rend « NA » (inconnue) si l'ancienneté est vide.
    """
    try:
        val = float(x)
    except Exception:
        return "NA"
    if not np.isfinite(val) or val < 0:
        return "NA"
    if val <= 2:
        return "0-2"
    if val <= 5:
        return "3-5"
    if val <= 12:
        return "6-12"
    if val <= 20:
        return "13-20"
    return ">20"


def preparer_employes(chemin_employes, chemin_bands, chemin_market) -> pd.DataFrame:
    """Lit les trois fichiers et rend le DataFrame des salariés prétraité.

    Étapes :
    1. Lire les trois fichiers Excel (.xlsx).
    2. Retirer les doublons : matricule en double chez les salariés, métier + grade en double dans la
       grille et le marché (le premier est gardé).
    3. Ajouter la tranche d'ancienneté de chaque salarié (Anciennete_Bucket).
    4. Ajouter à chaque salarié la fourchette de sa grille (Min, Mid, Max) et la médiane du marché
       (Market_Median), retrouvées grâce à son métier (Job_Family) et son grade (Grade).
    5. Calculer les ratios :
       - CompaRatio = salaire / Mid : 1 veut dire « payé au milieu de la fourchette » ;
       - RangePenetration = (salaire - Min) / (Max - Min) : 0 veut dire « au Min », 1 « au Max » ;
       - MarketRatio = salaire / médiane du marché : 1 veut dire « payé au niveau du marché ».
    """
    # 1. Lecture des trois fichiers. Ce sont des fichiers Excel : pas de séparateur ni d'encodage à
    # préciser, les nombres arrivent déjà comme des nombres.
    emp = pd.read_excel(chemin_employes)
    bands = pd.read_excel(chemin_bands)
    market = pd.read_excel(chemin_market)

    # 2. Doublons, dans les trois fichiers : on garde toujours le premier.
    cles = ["Job_Family", "Grade"]
    # Salariés : un même matricule présent deux fois.
    emp = emp.drop_duplicates(subset="Matricule")
    # Grille et marché : un même métier + grade présent deux fois. Sinon, chaque salarié concerné
    # serait recopié deux fois dans le DataFrame à l'étape 4.
    bands = bands.drop_duplicates(subset=cles)
    market = market.drop_duplicates(subset=cles)

    # 3. Tranche d'ancienneté
    # salarié aux collègues d'ancienneté proche.
    emp["Anciennete_Bucket"] = emp["Anciennete"].apply(bucket_anciennete)

    # 4. Grille et marché, retrouvés par métier + grade.
    grille = bands[cles + ["Min", "Mid", "Max"]]
    marche = market[cles + ["Median"]].rename(columns={"Median": "Market_Median"})
    # how="left" : on garde tous les salariés, même ceux dont le métier + grade n'existe pas dans la
    # grille ou le marché (leurs colonnes Min, Mid, Max ou Market_Median restent alors vides).
    df = emp.merge(grille, on=cles, how="left").merge(marche, on=cles, how="left")

    # 5. Ratios.
    # Pourquoi replace(0, np.nan) : un Mid, un écart Max - Min ou une médiane du marché égal à 0
    # ferait une division par zéro (un ratio « infini »). Le ratio reste vide à la place.
    df["CompaRatio"] = df["Fixe_Annuel_MAD"] / df["Mid"].replace(0, np.nan)
    df["RangePenetration"] = (df["Fixe_Annuel_MAD"] - df["Min"]) / (df["Max"] - df["Min"]).replace(0, np.nan)
    df["MarketRatio"] = df["Fixe_Annuel_MAD"] / df["Market_Median"].replace(0, np.nan)

    return df


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_pretraitement.py),
# pas quand un autre programme fait « from anomaly_pretraitement import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_pretraitement.py).
    projet = Path(__file__).resolve().parent.parent

    df = preparer_employes(projet / "input" / "employes.xlsx",
                           projet / "input" / "bands.xlsx",
                           projet / "input" / "market.xlsx")
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, en fichier Excel (.xlsx) : il s'ouvre directement, sans souci de
    # séparateur, de virgule décimale ou d'accents.
    sortie = projet / "output" / "pretraitement" / "employes_pretraites.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
