#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PROGRAMME PRINCIPAL : ENCHAÎNER TOUTES LES ÉTAPES
=================================================

Ce fichier enchaîne les étapes du dossier src/, dans l'ordre, et enregistre les résultats :
1. anomaly_pretraitement.py        : lecture, doublons, grille, marché, ratios, diplômes ;
2. anomaly_cohortes.py             : groupes de collègues et écart PeerZ ;
3. anomaly_regles.py               : règles (étiquettes, points, motifs) ;
4. anomaly_signal_iforest.py       : score de l'IA (écart au salaire attendu, ou Isolation Forest selon ml_methode) ;
5. anomaly_signal_fort.py          : signal ML_STRONG_SIGNAL pour les profils très atypiques, avec son explication (sans points) ;
6. anomaly_score_general.py        : score général (règles + IA) et priorité de chaque salarié ;
7. anomaly_recommandations.py      : recommandation et coût d'ajustement ;
8. anomaly_ecarts_hommes_femmes.py : médianes femmes / hommes par métier + niveau ;
9. generate_dashboard_html.py      : tableau de bord HTML ;
10. generate_accueil.py            : écran d'accueil (accueil.html), qui ouvre les trois outils.

Utilisation, depuis le dossier du projet :
      python src/detect_salary_anomalies.py
Les résultats sont enregistrés :
- dans output/detection/ : anomalies.xlsx et gender_gap.xlsx, à ouvrir avec Excel ;
- dans output/dashboard/ : le tableau de bord, sous un nom daté
  (dashboard_anomalies_AAAA-MM-JJ_HH-MM-SS.html), à ouvrir avec un navigateur.
"""

import time
from pathlib import Path

import yaml

from anomaly_pretraitement import message_diplomes, preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import ml_anomaly
from anomaly_signal_fort import apply_ml_strong_signal
from anomaly_score_general import aggregate_risk
from anomaly_recommandations import recommendations
from anomaly_ecarts_hommes_femmes import gender_gap_analysis
from generate_dashboard_html import generate_dashboard
from generate_accueil import generate_accueil


def secondes(debut):
    """Le temps écoulé depuis debut, écrit à la française : « 2,4 s »."""
    return f"{time.perf_counter() - debut:.1f} s".replace(".", ",")


def lancer(numero, texte, fonction, *arguments):
    """Lance une étape en affichant dans le terminal où on en est, puis le temps qu'elle a pris."""
    # flush=True : la ligne s'affiche tout de suite, avant que l'étape (parfois longue) ne commence.
    print(f"[{numero}/10] {texte}...", end=" ", flush=True)
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
    df = lancer(1, "Prétraitement (lecture, doublons, grille, marché, ratios, diplômes)", preparer_employes,
                projet / "input" / "employes.xlsx", projet / "input" / "bands.xlsx", projet / "input" / "market.xlsx")
    # Combien de salariés ont un diplôme connu ? Dit tout de suite, sous la ligne de l'étape : si les
    # colonnes du diplôme manquent dans employes.xlsx, on le voit avant d'aller lire les résultats.
    print("      " + message_diplomes(df))
    df = lancer(2, "Groupes de collègues (cohortes)", former_cohortes, df, rule_params)
    df = lancer(3, "Règles", apply_rulebook, df, rule_params)
    methode = {"ecart_attendu": "écart au salaire attendu", "isolation_forest": "Isolation Forest"}.get(
        rule_params.get("ml_methode", "isolation_forest"), rule_params.get("ml_methode"))
    df = lancer(4, f"Score de l'IA ({methode})", ml_anomaly, df, rule_params)
    df = lancer(5, "Signal fort de l'IA", apply_ml_strong_signal, df, rule_params)
    df = lancer(6, "Score général et priorité", aggregate_risk, df, rule_params)
    df = lancer(7, "Recommandations et coût d'ajustement", recommendations, df, rule_params)
    # Un tableau à part : une ligne par métier + niveau.
    gg = lancer(8, "Écarts hommes / femmes", gender_gap_analysis, df)

    # Les colonnes les plus utiles en premier, toutes les autres ensuite.
    # Les colonnes du diplôme juste après le niveau du poste : on lit le salaire en sachant déjà quel
    # diplôme a le salarié. Le rang (0 à 7) suit le niveau d'études, pour pouvoir trier dans le bon ordre.
    front_cols = ["Matricule", "Nom", "Entite_N1", "Entite_N2", "Job_Family", "Job_Title", "Niveau",
                  "Niveau_Etude_Max", "Rang_Etude_Max", "Tranche_Etude", "Cat_Ecole_Max",
                  "Fixe_Annuel_MAD", "Min", "Mid", "Max", "CompaRatio", "RangePenetration",
                  "Market_Median", "MarketRatio", "PeerZ", "Rule_Flags", "Rule_Score",
                  "Salaire_Attendu", "Attendu_Bas", "Attendu_Haut", "Ecart_Attendu", "Z_Attendu",
                  "ML_AnomalyScore", "RiskScore", "Severity", "Cohort_Key", "Reason_Principale", "Explication_IA", "Reco",
                  "Cout_Ajustement"]
    # Les colonnes du salaire attendu n'existent qu'avec ml_methode: ecart_attendu.
    front_cols = [c for c in front_cols if c in df.columns]
    df = df[front_cols + [c for c in df.columns if c not in front_cols]]

    # Tous les tableaux de bord au même endroit, quel que soit le programme qui les crée.
    tableau_de_bord = lancer(9, "Tableau de bord", generate_dashboard, df, gg, rule_params,
                             projet / "output" / "dashboard")

    # L'écran d'accueil, à la racine du projet : ses chiffres et son lien suivent ce tableau de bord.
    accueil = lancer(10, "Écran d'accueil", generate_accueil, df, tableau_de_bord, projet)

    # En fichiers Excel (.xlsx) : ils s'ouvrent directement, sans souci de séparateur, de virgule
    # décimale ou d'accents.
    df.to_excel(dossier / "anomalies.xlsx", index=False)
    gg.to_excel(dossier / "gender_gap.xlsx", index=False)

    print(f"\nTerminé en {secondes(debut)} : {len(df)} salariés analysés.")
    print(f"- Excel (anomalies.xlsx, gender_gap.xlsx) : {dossier}")
    print(f"- Tableau de bord : {tableau_de_bord}")
    print(f"- Écran d'accueil, à ouvrir en premier : {accueil}")
