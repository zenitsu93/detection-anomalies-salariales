#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RÈGLES : REPÉRER LES SALAIRES HORS DES CLOUS
============================================

Ce fichier applique les règles du fichier de règles (config/rules.yaml) au DataFrame rendu par
anomaly_cohortes.py (DataFrame prétraité + groupe de collègues de chaque salarié) et rend ce DataFrame
complété de trois colonnes :
- Rule_Flags : les règles déclenchées, séparées par « ; » (par exemple « OUT_OF_BAND;COMPA_RATIO ») ;
- Rule_Score : le total des points de ces règles ;
- Reason_Principale : les motifs en clair, séparés par « & ».
Ce DataFrame est ensuite l'entrée d'anomaly_signal_iforest.py.

Utilisation :
- depuis Python :
      from anomaly_regles import apply_rulebook
      df = apply_rulebook(df, rule_params)
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_regles.py
  Le DataFrame est enregistré dans output/regles/employes_regles.xlsx, à ouvrir avec Excel.
"""

from pathlib import Path

import pandas as pd
import yaml

from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes


def apply_rulebook(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Applique les cinq règles à chaque salarié et rend un NOUVEAU DataFrame (celui reçu n'est pas
    modifié).

    Ce qu'on lui donne : le DataFrame rendu par former_cohortes (anomaly_cohortes.py), qui contient les
    ratios, l'écart aux collègues (PeerZ), le grade (Grade) et le salaire (Fixe_Annuel_MAD).

    """
    # Les réglages, lus dans le fichier de règles (la valeur par défaut s'ils n'y sont pas).
    weights = rule_params.get("severity_weights")
    low_buf = rule_params.get("range_penetration_low_buffer")
    high_buf = rule_params.get("range_penetration_high_buffer")
    compa_lo = rule_params.get("compa_ratio_low")
    compa_hi = rule_params.get("compa_ratio_high")
    market_lo = rule_params.get("market_low")
    market_hi = rule_params.get("market_high")
    z_minor = rule_params.get("peer_z_threshold_minor")
    z_major = rule_params.get("peer_z_threshold_major")
    planchers = rule_params.get("min_salary_by_grade")

    df = df.copy()

    # Qui déclenche quoi : vrai ou faux pour chaque salarié. Une case vide donne toujours « faux ».
    sous_min = df["RangePenetration"] < low_buf
    au_dessus_max = df["RangePenetration"] > 1 + high_buf
    compa_bas = df["CompaRatio"] < compa_lo
    compa_haut = df["CompaRatio"] > compa_hi
    marche_bas = df["MarketRatio"] < market_lo
    marche_haut = df["MarketRatio"] > market_hi
    # abs() enlève le signe : payé nettement plus OU nettement moins que ses collègues, les deux comptent.
    pairs_minor = df["PeerZ"].abs() >= z_minor
    pairs_major = df["PeerZ"].abs() >= z_major
    # Le plancher du grade de chaque salarié. Un grade absent du fichier de règles reste vide : jamais
    # d'alerte. Exemple : grade 5, plancher 140 : un salaire de 135 déclenche l'alerte, 140 non.
    plancher = df["Grade"].map(planchers)
    sous_plancher = df["Fixe_Annuel_MAD"] < plancher

    # Étiquettes et points : pour chaque règle déclenchée, on ajoute « ;ETIQUETTE » et ses points.
    df["Rule_Flags"] = ""
    df["Rule_Score"] = 0.0
    df.loc[sous_min | au_dessus_max, "Rule_Flags"] += "OUT_OF_BAND"
    df.loc[sous_min | au_dessus_max, "Rule_Score"] += weights.get("out_of_band")
    df.loc[compa_bas | compa_haut, "Rule_Flags"] += ";COMPA_RATIO"
    df.loc[compa_bas | compa_haut, "Rule_Score"] += weights.get("compa_ratio")
    df.loc[marche_bas | marche_haut, "Rule_Flags"] += ";MARKET_GAP"
    df.loc[marche_bas | marche_haut, "Rule_Score"] += weights.get("market_gap")
    df.loc[pairs_minor, "Rule_Flags"] += ";PEER_OUTLIER"
    df.loc[pairs_major, "Rule_Score"] += weights.get("peer_outlier")
    df.loc[sous_plancher, "Rule_Flags"] += ";MIN_SALARY"
    df.loc[sous_plancher, "Rule_Score"] += weights.get("min_salary")

    df["Rule_Flags"] = df["Rule_Flags"].str.lstrip(";")

    # Motifs en clair : même principe, avec « & » entre deux motifs.
    # Pourquoi ce changement par rapport à l'archive : elle écrivait le motif salarié par salarié
    # (df.apply), ce qui est très lent sur 10 000 personnes. Ici, chaque motif est ajouté d'un coup à
    # tous les salariés concernés. Le texte obtenu est le même.
    compa_txt = df["CompaRatio"].map("{:.2f}".format)
    # « {:g} » écrit le plancher sans décimale inutile : 140 et non 140.0.
    plancher_txt = plancher.map("{:g}".format)
    df["Reason_Principale"] = ""
    df.loc[sous_min, "Reason_Principale"] += " & Salaire sous MIN interne"
    df.loc[au_dessus_max, "Reason_Principale"] += " & Salaire au-dessus du MAX interne"
    df.loc[compa_bas, "Reason_Principale"] += " & CompaRatio=" + compa_txt[compa_bas] + f" (<{compa_lo})"
    df.loc[compa_haut, "Reason_Principale"] += " & CompaRatio=" + compa_txt[compa_haut] + f" (>{compa_hi})"
    df.loc[marche_bas, "Reason_Principale"] += " & Sous la mediane marche"
    df.loc[marche_haut, "Reason_Principale"] += " & Au-dessus de la mediane marche"
    df.loc[pairs_major, "Reason_Principale"] += f" & Outlier vs pairs (|Z|> ou = {z_major:.1f})"
    df.loc[sous_plancher, "Reason_Principale"] += (" & Salaire sous le minimum du grade ("
                                                   + plancher_txt[sous_plancher] + ")")
    # Le « & » du début ne sert à rien non plus.
    df["Reason_Principale"] = df["Reason_Principale"].str.removeprefix(" & ")

    return df


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_regles.py),
# pas quand un autre programme fait « from anomaly_regles import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_regles.py).
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
    # 3. Règles : étiquettes, points et motifs (ce fichier).
    df = apply_rulebook(df, rule_params)
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, en fichier Excel (.xlsx) : il s'ouvre directement, sans souci de
    # séparateur, de virgule décimale ou d'accents.
    sortie = projet / "output" / "regles" / "employes_regles.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
