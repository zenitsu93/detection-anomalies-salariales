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


def main():
    ap = argparse.ArgumentParser(description="Detection des incohérences de rémunération fixe (custom).")
    ap.add_argument("--employees", required=True, help="Fichier CSV des employés (cp1252, séparateur ';')")
    ap.add_argument("--bands", required=True, help="Fichier CSV des fourchettes internes")
    ap.add_argument("--market", required=False, default=None, help="Fichier CSV du benchmark marché")
    ap.add_argument("--rulebook", required=True, help="Fichier YAML décrivant les règles et paramètres")
    ap.add_argument("--output", required=True, help="Fichier CSV de sortie (anomalies)")
    ap.add_argument("--excel-output", required=False, default=None, help="Fichier Excel de sortie (optionnel)")
    ap.add_argument("--gender-output", required=False, default=None, help="Fichier CSV de synthèse des écarts par sexe")
    args = ap.parse_args()

    # Chargement des données
    # Chargement avec détection du séparateur
    emp = read_csv_guess_sep(args.employees)
    bands = read_csv_guess_sep(args.bands)
    market = read_csv_guess_sep(args.market) if args.market else None

    # Suppression des colonnes dupliquées sur les employés (ex: double colonne Matricule)
    emp = remove_duplicate_columns(emp)
    # Le périmètre couvre un seul pays : aucune clé géographique supplémentaire.
    for table in (emp, bands, market):
        if table is not None and "Pays" in table.columns:
            table.drop(columns=["Pays"], inplace=True)

    # Lecture du rulebook
    with open(args.rulebook, "r", encoding="utf-8") as f:
        rulebook = yaml.safe_load(f) or {}
    rule_params = rulebook.get("rules", {})
    validate_rule_params(rule_params)

    # Calcul des métriques et des scores
    df = compute_features(emp, bands, market)
    df = apply_rulebook(df, rule_params)
    df = cohort_stats_and_peers_nv(df, rule_params)
    df = ml_anomaly(df, rule_params)
    df = apply_ml_strong_signal(df, rule_params)
    df = aggregate_risk(df, rule_params)
    df = recommendations(df)

    # Construction de la sortie organisée (front_cols) sans la colonne Ville (supprimée)
    front_cols = [c for c in [
        "Matricule", "Nom", "Entite_N1", "Entite_N2", "Pays", "Job_Family", "Job_Title", "Grade",
        "Fixe_Annuel_MAD", "Min", "Mid", "Max", "CompaRatio", "RangePenetration", "Market_Median", "MarketRatio",
        "PeerZ", "Rule_Flags", "Rule_Score", "ML_AnomalyScore", "RiskScore", "Severity", "Cohort_Key",
        "Reason_Principale", "Reco", "Cout_Ajustement"
    ] if c in df.columns]
    other_cols = [c for c in df.columns if c not in front_cols]
    out = df[front_cols + other_cols].copy()

    # Mise en forme des champs numériques (séparateur de milliers)
    out = format_numeric_fields(out)

    # Export CSV
    out.to_csv(args.output, index=False, encoding="utf-8")
    print(f"[OK] Export CSV: {args.output} - {len(out)} lignes")

    # Export Excel si demandé
    if args.excel_output:
        to_excel_colored(out, args.excel_output)
        print(f"[OK] Export Excel: {args.excel_output}")

    # Analyse des écarts par sexe si demandé
    if args.gender_output:
        try:
            gender_df = gender_gap_analysis(df)
            # Mise en forme de la colonne du ratio M/F avec deux décimales
            if "M_div_F" in gender_df.columns:
                gender_df["M_div_F"] = gender_df["M_div_F"].apply(lambda x: round(x, 2) if pd.notna(x) else np.nan)
            gender_df.to_csv(args.gender_output, index=False, encoding="utf-8")
            print(f"[OK] Export Gender Gap: {args.gender_output}")
        except Exception as e:
            print(f"[WARN] Impossible de réaliser l'analyse des écarts par sexe: {e}", file=sys.stderr)



if __name__ == "__main__":
    main()
