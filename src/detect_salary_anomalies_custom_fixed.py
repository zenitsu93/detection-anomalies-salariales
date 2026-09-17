#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Détection des incohérences de rémunération fixe (version personnalisée, corrigée).

Point d'entrée en ligne de commande : ce fichier ne fait que lire les arguments, charger les
fichiers d'entrée, appeler les fonctions de calcul dans le bon ordre, puis écrire les fichiers
de sortie (CSV, Excel, écarts homme/femme). Le code est réparti dans deux modules importés
ci-dessous, pour rester facile à relire :

- anomaly_core.py : toute la logique de détection (ratios, règles, cohortes, IA, agrégation,
  recommandations, écarts homme/femme). C'est le fichier le plus important si vous voulez
  comprendre ou ajuster la façon dont une anomalie est repérée.
- anomaly_io.py    : lecture des fichiers CSV, nettoyage des colonnes dupliquées, mise en forme
  des nombres et export Excel/CSV. Rien dans ce fichier n'influence le résultat de la détection.

Ce découpage est une réorganisation du code (lisibilité/maintenance) : le comportement du script
est inchangé par rapport à la version précédente en un seul fichier. Voir corrections.txt et
explication_simple.txt pour l'historique des corrections apportées au fil des relectures.

En entrée, les fichiers CSV doivent être encodés en cp1252 et utiliser un séparateur point‑virgule
(« ; »). Le fichier de règles YAML doit contenir les paramètres de détection (poids, seuils, etc.).

Utilisation :

```
python detect_salary_anomalies_custom_fixed.py \
  --employees chemin/vers/employes.csv \
  --bands chemin/vers/bands.csv \
  --market chemin/vers/market.csv \
  --rulebook chemin/vers/config/rules.yaml \
  --output chemin/vers/anomalies.csv \
  [--excel-output chemin/vers/anomalies.xlsx] \
  [--gender-output chemin/vers/gender_gap_analysis.csv]
```
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import yaml
except ImportError as e:
    raise SystemExit("PyYAML est requis. Installez-le via: pip install pyyaml") from e

from anomaly_core import (
    compute_features,
    apply_rulebook,
    apply_ml_strong_signal,
    cohort_stats_and_peers_nv,
    ml_anomaly,
    aggregate_risk,
    recommendations,
    gender_gap_analysis,
    validate_rule_params,
)
from anomaly_io import (
    remove_duplicate_columns,
    read_csv_guess_sep,
    format_numeric_fields,
    to_excel_colored,
)
from generate_dashboard_html import generate_dashboard


def main():
    ap = argparse.ArgumentParser(description="Detection des incohérences de rémunération fixe (custom).")
    ap.add_argument("--employees", required=True, help="Fichier CSV des employés (cp1252, séparateur ';')")
    ap.add_argument("--bands", required=True, help="Fichier CSV des fourchettes internes")
    ap.add_argument("--market", required=False, default=None, help="Fichier CSV du benchmark marché")
    ap.add_argument("--rulebook", required=True, help="Fichier YAML décrivant les règles et paramètres")
    ap.add_argument("--output", required=True, help="Fichier CSV de sortie (anomalies)")
    ap.add_argument("--excel-output", required=False, default=None, help="Fichier Excel de sortie (optionnel)")
    ap.add_argument("--gender-output", required=False, default=None, help="Fichier CSV de synthèse des écarts par sexe")
    # Pourquoi ces deux options : le dashboard HTML est désormais généré automatiquement à la
    # fin du traitement. --html-output permet de choisir où l'écrire, --no-html de s'en passer
    # (ex. exécution rapide ou tests, quand seuls les fichiers CSV/Excel sont utiles).
    ap.add_argument("--html-output", required=False, default=None,
                     help="Fichier HTML du dashboard interactif (par défaut: dashboard_anomalies.html à côté de --output)")
    ap.add_argument("--no-html", action="store_true", help="Ne pas générer le dashboard HTML")
    args = ap.parse_args()
    # Pourquoi (correction) : si le dossier de sortie n'existait pas (ex. output/ absent juste
    # après un clone), le script plantait à la toute fin, au moment d'écrire les fichiers.
    # On crée donc les dossiers manquants dès le départ.
    for output_path in (args.output, args.excel_output, args.gender_output, args.html_output):
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Chargement des données avec détection du séparateur
    emp = read_csv_guess_sep(args.employees)
    bands = read_csv_guess_sep(args.bands)
    market = read_csv_guess_sep(args.market) if args.market else None

    # Suppression des colonnes dupliquées sur les employés (ex: double colonne Matricule)
    emp = remove_duplicate_columns(emp)

    # Pourquoi (correction) : l'ancienne étape de renommage des colonnes (standardize_all) utilisait
    # des dictionnaires désactivés (placés entre guillemets), ce qui faisait planter le script. Elle a
    # été retirée : les fichiers utilisent déjà les bons noms de colonnes. À la place, on retire
    # seulement la colonne Pays, identique pour tout le monde.
    # Le pays est fixe pour ce client : la colonne n'apporte aucune information et est retirée
    for _df in (emp, bands, market):
        if _df is not None and "Pays" in _df.columns:
            _df.drop(columns=["Pays"], inplace=True)

    # remove_duplicate_columns ne traite que les colonnes dupliquées, pas les lignes : un même
    # Matricule présent deux fois (saisie en double, export dupliqué...) passe silencieusement,
    # et compte deux fois dans les cohortes, l'analyse de genre et les totaux budgétaires.
    if "Matricule" in emp.columns:
        dup_matricule = emp["Matricule"].duplicated(keep=False)
        if dup_matricule.any():
            n_dup = int(emp["Matricule"].duplicated(keep="first").sum())
            print(
                f"[WARN] {n_dup} Matricule(s) en double dans le fichier employés - ces lignes sont "
                "conservées telles quelles (comptées plusieurs fois dans les cohortes et les totaux).",
                file=sys.stderr,
            )

    # Lecture et validation du rulebook
    with open(args.rulebook, "r", encoding="utf-8") as f:
        rulebook = yaml.safe_load(f) or {}
    rule_params = rulebook.get("rules", {})
    # Pourquoi : avant, un paramètre absent ou mal nommé dans le fichier de règles était remplacé
    # en silence par une valeur par défaut. On affiche maintenant un avertissement pour chacun.
    validate_rule_params(rule_params)

    # Calcul des métriques et des scores (logique dans anomaly_core.py)
    df = compute_features(emp, bands, market)
    df = apply_rulebook(df, rule_params)
    df = cohort_stats_and_peers_nv(df, rule_params)
    df = ml_anomaly(df, rule_params)
    df = apply_ml_strong_signal(df, rule_params)
    df = aggregate_risk(df, rule_params)
    # Pourquoi rule_params est passé ici (correction) : avant, recommendations() utilisait des
    # seuils CompaRatio écrits en dur (0.85 / 1.15). Si le rulebook définissait d'autres seuils,
    # la détection et les recommandations ne suivaient pas les mêmes règles. Les deux lisent
    # maintenant les mêmes valeurs (compa_ratio_low / compa_ratio_high).
    df = recommendations(df, rule_params)

    # Les flags accumulés commencent chacun par ";" (";OUT_OF_BAND;COMPA_RATIO...") : on retire
    # le séparateur de tête une fois tous les flags posés.
    df["Rule_Flags"] = df["Rule_Flags"].astype(str).str.lstrip(";")

    # Pourquoi "Pays" n'est plus dans la liste ci-dessous : la colonne est supprimée plus haut
    # (pays unique), la garder ici n'avait plus de sens.
    # Construction de la sortie organisée (front_cols)
    front_cols = [c for c in [
        "Matricule", "Nom", "Entite_N1", "Entite_N2", "Job_Family", "Job_Title", "Grade",
        "Fixe_Annuel_MAD", "Min", "Mid", "Max", "CompaRatio", "RangePenetration", "Market_Median", "MarketRatio",
        "PeerZ", "Rule_Flags", "Rule_Score", "ML_AnomalyScore", "RiskScore", "Severity", "Cohort_Key",
        "Reason_Principale", "Reco", "Cout_Ajustement"
    ] if c in df.columns]
    other_cols = [c for c in df.columns if c not in front_cols]
    out_numeric = df[front_cols + other_cols].copy()

    # Pourquoi deux tableaux (out_numeric / out_csv) : avant, la mise en forme des montants
    # (format_numeric_fields) était appliquée à un seul tableau "out", réutilisé ensuite pour
    # l'Excel. Les montants arrivaient donc dans Excel sous forme de texte ("12 345,00") :
    # impossible de les additionner, trier ou filtrer, et la synthèse budgétaire ne pouvait pas
    # les totaliser. Désormais le CSV reçoit une copie formatée, et l'Excel garde les vrais nombres.
    # Export CSV : mise en forme lisible (séparateur de milliers, texte) sur une copie dédiée.
    out_csv = format_numeric_fields(out_numeric.copy())
    out_csv.to_csv(args.output, index=False, encoding="utf-8")
    print(f"[OK] Export CSV: {args.output} - {len(out_csv)} lignes")

    # Export Excel si demandé : à partir des valeurs numériques d'origine (pas de texte formaté),
    # la mise en forme "milliers" est appliquée au niveau des cellules Excel.
    if args.excel_output:
        to_excel_colored(out_numeric, args.excel_output)
        print(f"[OK] Export Excel: {args.excel_output}")

    # Analyse des écarts par sexe : toujours calculée (même sans --gender-output), car le
    # dashboard HTML en a besoin pour son graphique des écarts hommes/femmes.
    try:
        gender_df = gender_gap_analysis(df)
        # Mise en forme de la colonne du ratio M/F avec deux décimales
        if "M_div_F" in gender_df.columns:
            gender_df["M_div_F"] = gender_df["M_div_F"].apply(lambda x: round(x, 2) if pd.notna(x) else np.nan)
    except Exception as e:
        print(f"[WARN] Impossible de réaliser l'analyse des écarts par sexe: {e}", file=sys.stderr)
        # Pourquoi ce tableau vide : gender_df est maintenant utilisé après ce bloc (export,
        # dashboard). En cas d'échec de l'analyse, on le remplace par un tableau vide avec les
        # bonnes colonnes pour que la suite du script ne plante pas.
        gender_df = pd.DataFrame(columns=["Job_Family", "Grade", "Median_F", "Median_M", "M_div_F"])

    if args.gender_output:
        gender_df.to_csv(args.gender_output, index=False, encoding="utf-8")
        print(f"[OK] Export Gender Gap: {args.gender_output}")

    # Dashboard HTML (graphiques interactifs) : lit directement les résultats déjà calculés
    # ci-dessus (out_numeric, gender_df), sans repasser par le disque.
    if not args.no_html:
        html_path = args.html_output or str(Path(args.output).with_name("dashboard_anomalies.html"))
        generate_dashboard(df=out_numeric, gg=gender_df, out_html=html_path)
        print(f"[OK] Export Dashboard HTML: {html_path}")

if __name__ == "__main__":
    main()
