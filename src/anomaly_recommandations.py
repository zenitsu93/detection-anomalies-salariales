#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RECOMMANDATIONS : QUOI FAIRE, ET COMBIEN ÇA COÛTE
=================================================

Ce fichier donne à chaque salarié une recommandation (Reco) et le coût de l'ajustement proposé
(Cout_Ajustement), d'après sa place dans la grille (Min, Mid, Max) et son CompaRatio.

Il prend en entrée le DataFrame rendu par anomaly_signal_fort.py et rend ce DataFrame complété.

Utilisation :
- depuis Python :
      from anomaly_recommandations import recommendations
      df = recommendations(df, rule_params)
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_recommandations.py
  Le DataFrame est enregistré dans output/recommandations/employes_recommandations.xlsx, à ouvrir
  avec Excel.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import ml_anomaly
from anomaly_signal_fort import apply_ml_strong_signal


def recommendations(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Ajoute Reco et Cout_Ajustement et rend un NOUVEAU DataFrame (celui reçu n'est pas modifié).

    Les cas, testés dans cet ordre (seul le premier qui s'applique compte) :
    1. salaire sous le Min                        -> « Ajuster au MIN », coût = Min - salaire ;
    2. CompaRatio bas (< compa_ratio_low) et sous le Mid -> « Ajuster vers MID », coût = Mid - salaire ;
    3. salaire au-dessus du Max                   -> « Au-dessus MAX: Revue », coût 0 ;
    4. CompaRatio haut (> compa_ratio_high)       -> « Compa élevée: Revue », coût 0.
    Sinon : pas de recommandation, coût 0.
    """
    # Pourquoi lus dans le fichier de règles : l'archive écrivait 0.85 et 1.15 en dur, alors que les
    # règles lisent ces seuils dans config/rules.yaml. Les deux suivent maintenant les mêmes seuils.
    compa_lo = rule_params.get("compa_ratio_low")
    compa_hi = rule_params.get("compa_ratio_high")

    df = df.copy()
    fix, mn, md, mx, compa = df["Fixe_Annuel_MAD"], df["Min"], df["Mid"], df["Max"], df["CompaRatio"]

    # Une case vide donne toujours « faux » : sans grille, pas de recommandation.
    cas = [fix < mn, (compa < compa_lo) & (fix < md), fix > mx, compa > compa_hi]

    # Pourquoi np.select : il prend le premier cas vrai, comme les « if / elif » de l'archive, mais
    # d'un coup pour tous les salariés (l'archive les parcourait un par un, très lent sur 10 000).
    df["Reco"] = np.select(cas, ["Ajuster au MIN", "Ajuster vers MID", "Au-dessus MAX: Revue",
                                 "Compa élevée: Revue"], default="")
    df["Cout_Ajustement"] = np.select(cas[:2], [mn - fix, md - fix], default=0.0)

    return df


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_recommandations.py),
# pas quand un autre programme fait « from anomaly_recommandations import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_recommandations.py).
    projet = Path(__file__).resolve().parent.parent

    # Les réglages : la partie « rules: » du fichier de règles.
    with open(projet / "config" / "rules.yaml", encoding="utf-8") as fichier:
        rule_params = yaml.safe_load(fichier)["rules"]

    # Les étapes dans l'ordre : la sortie de chacune est l'entrée de la suivante.
    df = preparer_employes(projet / "input" / "employes.csv",
                           projet / "input" / "bands.csv",
                           projet / "input" / "market.csv")
    df = former_cohortes(df, rule_params)
    df = apply_rulebook(df, rule_params)
    df = ml_anomaly(df, rule_params)
    df = apply_ml_strong_signal(df, rule_params)
    # 6. Recommandations (ce fichier).
    df = recommendations(df, rule_params)
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, en fichier Excel (.xlsx) : il s'ouvre directement, sans souci de
    # séparateur, de virgule décimale ou d'accents.
    sortie = projet / "output" / "recommandations" / "employes_recommandations.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
