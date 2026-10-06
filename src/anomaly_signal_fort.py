#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SIGNAL FORT DE L'IA : UN SIXIÈME SIGNAL POUR LES PROFILS TRÈS ATYPIQUES
=======================================================================

Les cinq règles regardent le salaire sous un angle précis (grille, CompaRatio, marché, collègues,
salaire minimum). L'IA, elle, regarde tout le profil d'un coup (ML_AnomalyScore). Ce fichier fait
remonter ce qu'elle voit comme un sixième signal : les salariés parmi les plus atypiques pour l'IA
reçoivent l'étiquette ML_STRONG_SIGNAL et un motif, en plus des signaux des règles.

Ce signal n'ajoute aucun point : Rule_Score ne change pas. Le score de l'IA compte déjà dans le
score général (ml_weight dans config/rules.yaml) ; lui donner aussi des points le compterait deux
fois.

Il prend en entrée le DataFrame rendu par anomaly_signal_iforest.py et rend ce DataFrame complété.

Utilisation :
- depuis Python :
      from anomaly_signal_fort import apply_ml_strong_signal
      df = apply_ml_strong_signal(df, rule_params)
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_signal_fort.py
  Le DataFrame est enregistré dans output/signal_fort/employes_signal_fort.xlsx, à ouvrir avec Excel.
"""

from pathlib import Path

import pandas as pd
import yaml

from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import ml_anomaly


def apply_ml_strong_signal(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Ajoute l'étiquette ML_STRONG_SIGNAL aux salariés parmi les plus atypiques pour l'IA (les 5 % du
    haut avec ml_strong_signal_percentile = 0.95), qu'une règle se soit déclenchée ou non. Ne touche
    pas à Rule_Score. Rend un NOUVEAU DataFrame (celui reçu n'est pas modifié).

    On classe les salariés du score le plus faible au plus élevé, puis on prend le seuil au-dessus
    duquel se trouvent les 5 % du haut (sur 100 salariés, ce serait vers le 95ᵉ).
    """
    percentile = rule_params.get("ml_strong_signal_percentile")

    df = df.copy()

    # Le score à partir duquel on fait partie des plus atypiques.
    seuil = df["ML_AnomalyScore"].quantile(percentile)
    fort = df["ML_AnomalyScore"] >= seuil

    # Le signal et son motif s'ajoutent à ceux des règles, avec les mêmes séparateurs que dans
    # anomaly_regles.py (« ; » et « & »). Pour un salarié sans aucune règle déclenchée, il n'y avait
    # rien avant : on retire le séparateur resté en tête.
    df.loc[fort, "Rule_Flags"] += ";ML_STRONG_SIGNAL"
    df["Rule_Flags"] = df["Rule_Flags"].str.lstrip(";")
    df.loc[fort, "Reason_Principale"] += " & Profil atypique détecté par le modèle ML"
    df["Reason_Principale"] = df["Reason_Principale"].str.removeprefix(" & ")

    return df


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_signal_fort.py),
# pas quand un autre programme fait « from anomaly_signal_fort import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_signal_fort.py).
    projet = Path(__file__).resolve().parent.parent

    # Les réglages : la partie « rules: » du fichier de règles.
    with open(projet / "config" / "rules.yaml", encoding="utf-8") as fichier:
        rule_params = yaml.safe_load(fichier)["rules"]

    # Les étapes dans l'ordre : la sortie de chacune est l'entrée de la suivante.
    # 1. Prétraitement : lecture, doublons, grille, marché, ratios (anomaly_pretraitement.py).
    df = preparer_employes(projet / "input" / "employes.xlsx",
                           projet / "input" / "bands.xlsx",
                           projet / "input" / "market.xlsx")
    # 2. Groupes de collègues et écart PeerZ (anomaly_cohortes.py).
    df = former_cohortes(df, rule_params)
    # 3. Règles : étiquettes, points et motifs (anomaly_regles.py).
    df = apply_rulebook(df, rule_params)
    # 4. Score de l'IA (anomaly_signal_iforest.py).
    df = ml_anomaly(df, rule_params)
    # 5. Signal fort de l'IA (ce fichier).
    df = apply_ml_strong_signal(df, rule_params)
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, en fichier Excel (.xlsx) : il s'ouvre directement, sans souci de
    # séparateur, de virgule décimale ou d'accents.
    sortie = projet / "output" / "signal_fort" / "employes_signal_fort.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
