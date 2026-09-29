#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ÉCARTS HOMMES / FEMMES
======================

Ce fichier compare, pour chaque métier + grade, le salaire du milieu (la médiane) des femmes et des
hommes. Il rend un tableau à part (une ligne par métier + grade), pas le DataFrame des salariés :
- Median_F et Median_M : les médianes des femmes et des hommes ;
- M_div_F = Median_M / Median_F : au-dessus de 1, les hommes sont mieux payés ; en dessous, les
  femmes. Vide s'il manque les femmes ou les hommes dans ce métier + grade.

Il n'a besoin que du DataFrame rendu par anomaly_pretraitement.py (salaire, métier, grade, sexe).

Utilisation :
- depuis Python :
      from anomaly_ecarts_hommes_femmes import gender_gap_analysis
      gg = gender_gap_analysis(df)
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_ecarts_hommes_femmes.py
  Le tableau est enregistré dans output/ecarts_hommes_femmes/gender_gap.csv, à ouvrir avec Excel.
"""

from pathlib import Path

import pandas as pd

from anomaly_pretraitement import preparer_employes


def gender_gap_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Rend le tableau des médianes femmes / hommes par métier + grade, et leur ratio M_div_F."""
    # Une colonne par sexe (unstack), puis Median_F et Median_M comme noms.
    med = df.groupby(["Job_Family", "Grade", "Sexe"])["Fixe_Annuel_MAD"].median().unstack()
    med = med.rename(columns=lambda x: f"Median_{x}")
    med["M_div_F"] = med["Median_M"] / med["Median_F"]
    return med.reset_index()


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_ecarts_hommes_femmes.py),
# pas quand un autre programme fait « from anomaly_ecarts_hommes_femmes import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_ecarts_hommes_femmes.py).
    projet = Path(__file__).resolve().parent.parent

    df = preparer_employes(projet / "input" / "employes.csv",
                           projet / "input" / "bands.csv",
                           projet / "input" / "market.csv")
    gg = gender_gap_analysis(df)
    print(gg.head(10).to_string(index=False))

    sortie = projet / "output" / "ecarts_hommes_femmes" / "gender_gap.csv"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    gg.to_csv(sortie, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    print(f"\n{len(gg)} métiers + grades - tableau enregistré dans : {sortie}")
