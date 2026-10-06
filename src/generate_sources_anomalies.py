#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
DONNÉES FICTIVES AVEC ANOMALIES
===============================

generate_sources.py fabrique des salariés fictifs dont le salaire tombe toujours dans la grille de
leur métier + grade : la détection n'a presque rien à trouver. Ce fichier lance generate_sources.py,
puis abîme volontairement quelques salariés de input/employes.xlsx pour que la détection ait de
vraies anomalies à repérer :
- des salaires sous le Min de la grille, au-dessus du Max, ou très bas (sous le salaire minimum de
  leur grade) ;
- des matricules en double (une ligne recopiée à la fin du fichier).
Les autres salariés, la grille (bands.xlsx) et le marché (market.xlsx) ne changent pas.

Utilisation, depuis le dossier du projet :
      python src/generate_sources_anomalies.py
Attention : comme generate_sources.py, il réécrit les trois fichiers de input/.
"""

from pathlib import Path

import numpy as np
import pandas as pd

import generate_sources

# Pour chaque type : (part des salariés touchés, facteur bas, facteur haut, borne de la grille).
# Le salaire est remplacé par un tirage entre facteur bas × borne et facteur haut × borne.
# Un salarié ne reçoit qu'une seule anomalie. Mettre une part à 0 pour supprimer un type.
ANOMALIES = {
    # Sous la grille : entre 75 % et 90 % du Min (2 % des salariés).
    "SOUS_MIN": (0.02, 0.75, 0.90, "Min"),
    # Au-dessus de la grille : entre 110 % et 140 % du Max (1,5 % des salariés).
    "AU_DESSUS_MAX": (0.015, 1.10, 1.40, "Max"),
    # Très bas : entre 45 % et 60 % du Min (0,5 % des salariés). Avec les planchers de
    # min_salary_by_grade (config/rules.yaml), ces salaires tombent tous sous le salaire minimum.
    "TRES_BAS": (0.005, 0.45, 0.60, "Min"),
}
# Salariés recopiés une deuxième fois à la fin du fichier, avec le même matricule : l'analyse doit
# garder la première ligne.
N_DOUBLONS = 10


if __name__ == "__main__":
    # 1. Les données fictives sans anomalie (elles sont écrites dans input/).
    generate_sources.main()

    dossier = Path(__file__).resolve().parent.parent / "input"
    employes = pd.read_excel(dossier / "employes.xlsx")
    bands = pd.read_excel(dossier / "bands.xlsx")

    # 2. Les anomalies. Un tirage au sort à part (graine différente de celle de generate_sources) :
    # le même lancement donne toujours les mêmes anomalies, sur les mêmes salariés.
    rng = np.random.default_rng(generate_sources.SEED + 1)
    # Min et Max de la grille de chaque salarié, dans l'ordre des lignes.
    bornes = employes.merge(bands, on=["Pays", "Job_Family", "Grade"], how="left")
    # Les salariés encore sans anomalie (au départ, tout le monde).
    libres = np.arange(len(employes))
    for nom, (part, bas, haut, borne) in ANOMALIES.items():
        # Nombre de salariés touchés, par exemple 2 % de 10 000 = 200.
        n = int(round(len(employes) * part))
        idx = rng.choice(libres, size=n, replace=False)
        libres = np.setdiff1d(libres, idx)
        facteurs = rng.uniform(bas, haut, size=n)
        employes.loc[idx, "Fixe_Annuel_MAD"] = (facteurs * bornes.loc[idx, borne].to_numpy()).round(2)
        print(f"{nom} : {n} salariés")
    # Les doublons vont à la fin : la ligne d'origine reste la première.
    doublons = employes.loc[rng.choice(len(employes), size=N_DOUBLONS, replace=False)]
    employes = pd.concat([employes, doublons], ignore_index=True)
    print(f"Doublons : {N_DOUBLONS} matricules")

    employes.to_excel(dossier / "employes.xlsx", index=False)
    print(f"\n{len(employes)} lignes (dont {N_DOUBLONS} doublons) enregistrées dans : {dossier / 'employes.xlsx'}")
