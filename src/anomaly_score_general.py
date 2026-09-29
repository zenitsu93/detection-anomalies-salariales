#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SCORE GÉNÉRAL : UN SEUL SCORE ET UNE PRIORITÉ PAR SALARIÉ
=========================================================

Ce fichier réunit le score des règles (Rule_Score) et le score de l'IA (ML_AnomalyScore) en un seul
score général, puis en déduit la priorité de chaque salarié. Il prend en entrée le DataFrame rendu
par anomaly_signal_fort.py et rend ce DataFrame complété de deux colonnes :
- RiskScore = rule_weight × Rule_Score + ml_weight × ML_AnomalyScore (0.7 et 0.3 dans
  config/rules.yaml : les règles comptent pour 70 %, l'IA pour 30 %) ;
- Severity : la priorité, Critical, Major, Minor ou Info, selon les seuils de prioritization_buckets.

Utilisation :
- depuis Python :
      from anomaly_score_general import aggregate_risk
      df = aggregate_risk(df, rule_params)
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_score_general.py
  Le DataFrame est enregistré dans output/score_general/employes_score_general.csv, à ouvrir avec
  Excel.
"""

from pathlib import Path

import pandas as pd
import yaml

from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import ml_anomaly
from anomaly_signal_fort import apply_ml_strong_signal


def aggregate_risk(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Ajoute RiskScore et Severity et rend un NOUVEAU DataFrame (celui reçu n'est pas modifié)."""
    rule_w = rule_params.get("rule_weight")
    ml_w = rule_params.get("ml_weight")
    buckets = rule_params.get("prioritization_buckets")

    df = df.copy()
    df["RiskScore"] = rule_w * df["Rule_Score"] + ml_w * df["ML_AnomalyScore"]

    # Pourquoi seule la borne basse compte : l'archive vérifiait aussi la borne haute. Un score à
    # virgule entre deux niveaux, comme 69,4 (au-dessus de Major [50, 69], sous Critical [70, 100]),
    # ne tombait alors dans aucun niveau et finissait en « Info ». Ici, on part du niveau le plus bas
    # et chaque niveau prend tous les scores qui atteignent sa borne basse.
    # 1. Lire le score minimum d'un niveau. Exemple : pour Major [50, 69], on lit 50.
    def score_minimum(niveau):
        bornes = buckets[niveau]
        return bornes[0]

    # 2. Ranger les niveaux par score minimum croissant : Info, Minor, Major, Critical.
    niveaux_tries = sorted(buckets, key=score_minimum)

    # 3. Attribuer chaque niveau aux salariés qui atteignent son score minimum.
    # Le niveau suivant remplace le précédent si son seuil est lui aussi atteint.
    # Exemple pour 69,4 : Info, puis Minor, puis Major ; Critical ne s'applique pas.
    for niveau in niveaux_tries:
        borne_basse = score_minimum(niveau)
        seuil_atteint = df["RiskScore"] >= borne_basse
        df.loc[seuil_atteint, "Severity"] = niveau

    return df


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_score_general.py),
# pas quand un autre programme fait « from anomaly_score_general import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_score_general.py).
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
    # 6. Score général et priorité (ce fichier).
    df = aggregate_risk(df, rule_params)
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, pour Excel : séparateur « ; », virgule décimale, et encodage utf-8-sig
    # (pour qu'Excel affiche bien les accents).
    sortie = projet / "output" / "score_general" / "employes_score_general.csv"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(sortie, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
