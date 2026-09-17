#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Détection des incohérences de rémunération fixe - variante avec un 3e signal par régression
multivariée (OLS), en plus des règles déterministes et de l'IsolationForest.

Ce script est un point d'entrée en ligne de commande INDÉPENDANT de
detect_salary_anomalies_custom_fixed.py : il ne le modifie pas et ne le remplace pas. Il en
reprend la même structure et réutilise les mêmes fonctions de calcul pour les règles, les
cohortes et l'IsolationForest (anomaly_core.py) et pour la lecture/l'export des fichiers
(anomaly_io.py), toutes deux inchangées. Le seul ajout est le module anomaly_regression.py, qui
calcule un signal supplémentaire (Reg_AnomalyScore) à partir d'une régression prédisant le
salaire attendu de chaque employé, et une variante de l'agrégation du risque
(aggregate_risk_with_regression) qui combine 3 signaux au lieu de 2.

En entrée, les fichiers CSV doivent être encodés en cp1252 et utiliser un séparateur point‑virgule
(« ; »). Le fichier de règles YAML doit contenir les paramètres de détection (poids, seuils, etc.)
ainsi que les paramètres propres à la régression (rule_weight/ml_weight/reg_weight,
reg_min_category_size, reg_min_observations, reg_min_observations_per_param) - voir
config/rules_regression.yaml pour un exemple.

Utilisation :

```
python detect_salary_anomalies_regression.py \
  --employees chemin/vers/employes.csv \
  --bands chemin/vers/bands.csv \
  --market chemin/vers/market.csv \
  --rulebook chemin/vers/config/rules_regression.yaml \
  --output chemin/vers/anomalies_regression.csv \
  [--excel-output chemin/vers/anomalies_regression.xlsx] \
  [--gender-output chemin/vers/gender_gap_analysis.csv] \
  [--reg-gender-output chemin/vers/reg_gender_gap.csv]
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
    cohort_stats_and_peers_nv,
    ml_anomaly,
    apply_ml_strong_signal,
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
from anomaly_regression import (
    regression_anomaly,
    aggregate_risk_with_regression,
    regression_gender_gap_report,
    validate_regression_params,
)
from generate_dashboard_html import generate_dashboard


def main():
    ap = argparse.ArgumentParser(
        description="Detection des incoherences de remuneration fixe (regles + IsolationForest + regression)."
    )
    ap.add_argument("--employees", required=True, help="Fichier CSV des employés (cp1252, séparateur ';')")
    ap.add_argument("--bands", required=True, help="Fichier CSV des fourchettes internes")
    ap.add_argument("--market", required=False, default=None, help="Fichier CSV du benchmark marché")
    ap.add_argument("--rulebook", required=True, help="Fichier YAML décrivant les règles et paramètres")
    ap.add_argument("--output", required=True, help="Fichier CSV de sortie (anomalies)")
    ap.add_argument("--excel-output", required=False, default=None, help="Fichier Excel de sortie (optionnel)")
    ap.add_argument("--gender-output", required=False, default=None, help="Fichier CSV de synthèse des écarts par sexe")
    ap.add_argument("--reg-gender-output", required=False, default=None,
                     help="Fichier CSV du rapport d'écart Homme/Femme ajusté par la régression (optionnel)")
    ap.add_argument("--html-output", required=False, default=None,
                     help="Fichier HTML du dashboard interactif (par défaut: dashboard_anomalies_regression.html à côté de --output)")
    ap.add_argument("--no-html", action="store_true", help="Ne pas générer le dashboard HTML")
    args = ap.parse_args()
    for output_path in (args.output, args.excel_output, args.gender_output,
                        args.reg_gender_output, args.html_output):
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Chargement des données avec détection du séparateur
    emp = read_csv_guess_sep(args.employees)
    bands = read_csv_guess_sep(args.bands)
    market = read_csv_guess_sep(args.market) if args.market else None

    # Suppression des colonnes dupliquées sur les employés (ex: double colonne Matricule)
    emp = remove_duplicate_columns(emp)

    # Le pays est fixe pour ce client : la colonne n'apporte aucune information et est retirée
    for _df in (emp, bands, market):
        if _df is not None and "Pays" in _df.columns:
            _df.drop(columns=["Pays"], inplace=True)

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
    validate_rule_params(rule_params)
    validate_regression_params(rule_params)

    # Calcul des métriques et des scores : règles + cohortes + IsolationForest (anomaly_core.py,
    # inchangé) puis régression multivariée (anomaly_regression.py, nouveau signal).
    df = compute_features(emp, bands, market)
    df = apply_rulebook(df, rule_params)
    df = cohort_stats_and_peers_nv(df, rule_params)
    df = ml_anomaly(df, rule_params)
    df, reg_model = regression_anomaly(df, rule_params)
    df = apply_ml_strong_signal(df, rule_params)
    df = aggregate_risk_with_regression(df, rule_params)
    df = recommendations(df)

    df["Rule_Flags"] = df["Rule_Flags"].astype(str).str.lstrip(";")

    front_cols = [c for c in [
        "Matricule", "Nom", "Entite_N1", "Entite_N2", "Job_Family", "Job_Title", "Grade",
        "Fixe_Annuel_MAD", "Min", "Mid", "Max", "CompaRatio", "RangePenetration", "Market_Median", "MarketRatio",
        "PeerZ", "Rule_Flags", "Rule_Score", "ML_AnomalyScore",
        "Salaire_Predit_Regression", "Residu_Regression", "Reg_AnomalyScore",
        "RiskScore", "Severity", "Cohort_Key",
        "Reason_Principale", "Reco", "Cout_Ajustement"
    ] if c in df.columns]
    other_cols = [c for c in df.columns if c not in front_cols]
    out_numeric = df[front_cols + other_cols].copy()

    out_csv = format_numeric_fields(out_numeric.copy())
    out_csv.to_csv(args.output, index=False, encoding="utf-8")
    print(f"[OK] Export CSV: {args.output} - {len(out_csv)} lignes")

    if args.excel_output:
        to_excel_colored(out_numeric, args.excel_output)
        print(f"[OK] Export Excel: {args.excel_output}")

    try:
        gender_df = gender_gap_analysis(df)
        if "M_div_F" in gender_df.columns:
            gender_df["M_div_F"] = gender_df["M_div_F"].apply(lambda x: round(x, 2) if pd.notna(x) else np.nan)
    except Exception as e:
        print(f"[WARN] Impossible de réaliser l'analyse des écarts par sexe: {e}", file=sys.stderr)
        gender_df = pd.DataFrame(columns=["Job_Family", "Grade", "Median_F", "Median_M", "M_div_F"])

    if args.gender_output:
        gender_df.to_csv(args.gender_output, index=False, encoding="utf-8")
        print(f"[OK] Export Gender Gap: {args.gender_output}")

    # Rapport d'écart Homme/Femme "ajusté" (coefficient du Sexe une fois les facteurs de poste
    # et de carrière contrôlés) - complément statistique à gender_df ci-dessus, qui ne compare
    # que des médianes brutes.
    reg_gender_report = regression_gender_gap_report(reg_model, rule_params)
    if reg_gender_report.get("available"):
        print(
            "[INFO][REGRESSION] Ecart Homme/Femme ajuste (toutes choses egales par ailleurs) : "
            f"{reg_gender_report['pct_gap']:+.1f}% (p={reg_gender_report['pvalue']:.3f}, "
            f"IC95%=[{reg_gender_report['ci95_pct_low']:+.1f}%, {reg_gender_report['ci95_pct_high']:+.1f}%], "
            f"n={reg_gender_report['n_obs']})",
            file=sys.stderr,
        )
    else:
        print(f"[WARN][REGRESSION] Ecart Homme/Femme ajuste indisponible : {reg_gender_report.get('reason')}", file=sys.stderr)

    if args.reg_gender_output:
        pd.DataFrame([reg_gender_report]).to_csv(args.reg_gender_output, index=False, encoding="utf-8")
        print(f"[OK] Export Regression Gender Gap: {args.reg_gender_output}")

    if not args.no_html:
        html_path = args.html_output or str(Path(args.output).with_name("dashboard_anomalies_regression.html"))
        generate_dashboard(df=out_numeric, gg=gender_df, out_html=html_path)
        print(f"[OK] Export Dashboard HTML: {html_path}")

if __name__ == "__main__":
    main()
