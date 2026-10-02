#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PROGRAMME PRINCIPAL : ENCHAÎNER TOUTES LES ÉTAPES
=================================================

Ce fichier enchaîne les étapes du dossier src/, dans l'ordre, et enregistre les résultats :
1. anomaly_pretraitement.py        : lecture, doublons, grille, marché, ratios ;
2. anomaly_cohortes.py             : groupes de collègues et écart PeerZ ;
3. anomaly_regles.py               : règles (étiquettes, points, motifs) ;
4. anomaly_signal_iforest.py       : score de l'IA ;
5. anomaly_signal_fort.py          : signal ML_STRONG_SIGNAL pour les profils très atypiques (sans points) ;
6. anomaly_score_general.py        : score général (règles + IA) et priorité de chaque salarié ;
7. anomaly_recommandations.py      : recommandation et coût d'ajustement ;
8. anomaly_ecarts_hommes_femmes.py : médianes femmes / hommes par métier + grade ;
9. generate_dashboard_html.py      : tableau de bord HTML.

Utilisation, depuis le dossier du projet :
      python src/detect_salary_anomalies.py
Les résultats sont enregistrés :
- dans output/detection/ : anomalies.csv et gender_gap.csv, à ouvrir avec Excel ;
- dans output/dashboard/ : le tableau de bord, sous un nom daté
  (dashboard_anomalies_AAAA-MM-JJ_HH-MM-SS.html), à ouvrir avec un navigateur.
"""

import time
from pathlib import Path

import yaml

from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import ml_anomaly
from anomaly_signal_fort import apply_ml_strong_signal
from anomaly_score_general import aggregate_risk
from anomaly_recommandations import recommendations
from anomaly_ecarts_hommes_femmes import gender_gap_analysis
from generate_dashboard_html import generate_dashboard


def secondes(debut):
    """Le temps écoulé depuis debut, écrit à la française : « 2,4 s »."""
    return f"{time.perf_counter() - debut:.1f} s".replace(".", ",")


def lancer(numero, texte, fonction, *arguments):
    """Lance une étape en affichant dans le terminal où on en est, puis le temps qu'elle a pris."""
    # flush=True : la ligne s'affiche tout de suite, avant que l'étape (parfois longue) ne commence.
    print(f"[{numero}/9] {texte}...", end=" ", flush=True)
    debut = time.perf_counter()
    resultat = fonction(*arguments)
    print(f"fait en {secondes(debut)}")
    return resultat


if __name__ == "__main__":
    debut = time.perf_counter()
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/detect_salary_anomalies.py).
    projet = Path(__file__).resolve().parent.parent
    dossier = projet / "output" / "detection"
    dossier.mkdir(parents=True, exist_ok=True)

    # Les réglages : la partie « rules: » du fichier de règles.
    with open(projet / "config" / "rules.yaml", encoding="utf-8") as fichier:
        rule_params = yaml.safe_load(fichier)["rules"]

    # Les étapes dans l'ordre : la sortie de chacune est l'entrée de la suivante. Chacune affiche sa
    # ligne dans le terminal : on voit laquelle tourne et combien de temps elle a pris.
    df = lancer(1, "Prétraitement (lecture, doublons, grille, marché, ratios)", preparer_employes,
                projet / "input" / "employes.csv", projet / "input" / "bands.csv", projet / "input" / "market.csv")
    df = lancer(2, "Groupes de collègues (cohortes)", former_cohortes, df, rule_params)
    df = lancer(3, "Règles", apply_rulebook, df, rule_params)
    df = lancer(4, "Score de l'IA (Isolation Forest)", ml_anomaly, df, rule_params)
    df = lancer(5, "Signal fort de l'IA", apply_ml_strong_signal, df, rule_params)
    df = lancer(6, "Score général et priorité", aggregate_risk, df, rule_params)
    df = lancer(7, "Recommandations et coût d'ajustement", recommendations, df, rule_params)
    # Un tableau à part : une ligne par métier + grade.
    gg = lancer(8, "Écarts hommes / femmes", gender_gap_analysis, df)

    # Les colonnes les plus utiles en premier, toutes les autres ensuite.
    front_cols = ["Matricule", "Nom", "Entite_N1", "Entite_N2", "Job_Family", "Job_Title", "Grade",
                  "Fixe_Annuel_MAD", "Min", "Mid", "Max", "CompaRatio", "RangePenetration",
                  "Market_Median", "MarketRatio", "PeerZ", "Rule_Flags", "Rule_Score",
                  "ML_AnomalyScore", "RiskScore", "Severity", "Cohort_Key", "Reason_Principale", "Reco", "Cout_Ajustement"]
    df = df[front_cols + [c for c in df.columns if c not in front_cols]]

    # Tous les tableaux de bord au même endroit, quel que soit le programme qui les crée.
    tableau_de_bord = lancer(9, "Tableau de bord", generate_dashboard, df, gg, projet / "output" / "dashboard")

    # Pour Excel : séparateur « ; », virgule décimale, et encodage utf-8-sig (pour les accents).
    df.to_csv(dossier / "anomalies.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")
    gg.to_csv(dossier / "gender_gap.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")

    print(f"\nTerminé en {secondes(debut)} : {len(df)} salariés analysés.")
    print(f"- CSV (anomalies.csv, gender_gap.csv) : {dossier}")
    print(f"- Tableau de bord : {tableau_de_bord}")
