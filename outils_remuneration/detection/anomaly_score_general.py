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
- Severity : la priorité, Critical, Major, Minor ou Info, selon les seuils de prioritization_buckets ;
  plus une cinquième valeur, « Outlier positif », pour un salarié sans alerte payé au-dessus du Max de
  sa grille. Ce n'est pas une anomalie (rien à traiter), c'est une étiquette pour le reconnaître.

Utilisation :
- depuis Python :
      from anomaly_score_general import aggregate_risk
      df = aggregate_risk(df, rule_params)
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_score_general.py
  Le DataFrame est enregistré dans output/score_general/employes_score_general.xlsx, à ouvrir avec
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

# Le nom de la cinquième valeur de Severity. Les autres (Info, Minor, Major, Critical) sont dans
# config/rules.yaml avec leurs seuils ; celle-ci n'a pas de seuil de score, elle se lit sur la grille.
OUTLIER_POSITIF = "Outlier positif"


def aggregate_risk(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Ajoute RiskScore et Severity et rend un NOUVEAU DataFrame (celui reçu n'est pas modifié)."""
    rule_w = rule_params.get("rule_weight")
    ml_w = rule_params.get("ml_weight")
    buckets = rule_params.get("prioritization_buckets")

    df = df.copy()
    df["RiskScore"] = rule_w * df["Rule_Score"] + ml_w * df["ML_AnomalyScore"]

    # Pourquoi cette correction par rapport à l'archive ? Le score peut avoir des décimales,
    # mais l'ancien code vérifiait les deux bornes incluses, par exemple 50 <= score <= 69.
    # Avec un score de 69,4 :
    # - Major [50, 69] était refusé, car 69,4 > 69 ;
    # - Critical [70, 100] était refusé, car 69,4 < 70 ;
    # - aucun intervalle ne correspondait : le code renvoyait « Info » par défaut.
    # Un score proche de Critical se retrouvait donc à la priorité la plus basse.
    # On corrige ce trou entre les priorités en utilisant seulement leurs scores minimums :
    # Major commence à 50 et reste valable jusqu'à 70 exclu. Ainsi, 69,4 reste Major.
    # Le calcul du RiskScore ne change pas ; c'est son classement qui est corrigé.
    #
    # Les priorités sont déjà rangées dans le YAML : Info, Minor, Major, Critical.
    # Il faut conserver cet ordre croissant des bornes basses dans la configuration.
    # La priorité suivante remplace la précédente si son seuil est lui aussi atteint.
    # Exemple pour 69,4 : Info, puis Minor, puis Major ; Critical ne s'applique pas.
    for priorite in buckets:
        bornes = buckets[priorite]
        borne_basse = bornes[0]
        seuil_atteint = df["RiskScore"] >= borne_basse
        df.loc[seuil_atteint, "Severity"] = priorite

    # La cinquième valeur : « Outlier positif », pour un salarié payé AU-DESSUS du Max de sa grille.
    # Pourquoi : depuis le comité du 15/10/2026, être payé au-dessus de sa grille n'est pas une anomalie.
    # Ces salariés tombaient donc en « Info », mélangés aux salaires normaux. Or ils tirent les salaires
    # vers le haut et gênent la régression : il faut pouvoir les reconnaître, puis les retirer avec la
    # liste A_RETIRER des notebooks de régression.
    # Pourquoi seulement ceux qui étaient en « Info » : un salarié au-dessus du Max peut quand même être
    # signalé (sous le marché, sous ses collègues, sous le minimum de son niveau). Sa priorité Critical,
    # Major ou Minor reste alors en place : on ne cache jamais une alerte.
    # Exemple : Max = 300, salaire = 300 -> pas concerné ; salaire = 301 et « Info » -> « Outlier positif ».
    au_dessus_du_max = df["Fixe_Annuel_MAD"] > df["Max"]
    df.loc[au_dessus_du_max & (df["Severity"] == "Info"), "Severity"] = OUTLIER_POSITIF

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
    df = preparer_employes(projet / "input" / "employes.xlsx",
                           projet / "input" / "bands.xlsx",
                           projet / "input" / "market.xlsx")
    df = former_cohortes(df, rule_params)
    df = apply_rulebook(df, rule_params)
    df = ml_anomaly(df, rule_params)
    df = apply_ml_strong_signal(df, rule_params)
    # 6. Score général et priorité (ce fichier).
    df = aggregate_risk(df, rule_params)
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, en fichier Excel (.xlsx) : il s'ouvre directement, sans souci de
    # séparateur, de virgule décimale ou d'accents.
    sortie = projet / "output" / "score_general" / "employes_score_general.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    # Dans le fichier, les nombres calculés ont 2 chiffres après la virgule. Les calculs gardent toute leur précision.
    df.round(2).to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
