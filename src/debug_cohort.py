#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script isole pour deboguer cohort_stats_and_peers_nv() a la main.

Copie exacte de la fonction (et de sa dependance robust_zscore) depuis
detect_salary_anomalies_custom_commented.py, avec un petit jeu de donnees fait main
qui reprend l'exemple utilise dans nos explications :

- Groupe A (3 personnes, Grade=1, Job_Family="X", Anciennete_Bucket="0-2") -> trop petit
- Groupe B (2 personnes, Grade=1, Job_Family="X", Anciennete_Bucket="3-5") -> trop petit
  (A et B doivent fusionner en "1|X" au niveau Grade|Job_Family, taille finale 5)
- Groupe C (5 personnes, Grade=1, Job_Family="Y", Anciennete_Bucket="0-2") -> deja assez grand
  (doit rester a "1|Y|0-2", jamais elargi ni fusionne avec A/B)
- B2 a un salaire tres eloigne (500) pour observer un PEER_OUTLIER "majeur".

Pour deboguer :
- Lancez ce script tel quel pour voir les impressions a chaque etape cle.
- Ou posez un point d'arret (breakpoint) dans votre IDE sur n'importe quelle ligne
  de cohort_stats_and_peers_nv() ci-dessous, et lancez ce fichier en mode debug.
- Vous pouvez aussi modifier librement `df_test` plus bas pour tester d'autres cas
  (cohortes encore plus petites, valeurs differentes, etc.).
"""

from pathlib import Path

import numpy as np
import pandas as pd

# Le jeu de donnees de test (debug_cohort_data.csv) vit dans tests/data/, alors que ce script vit dans
# src/ (reorganisation du projet en src/ + input/ + tests/) : on calcule son chemin a partir
# de l'emplacement de CE fichier plutot que du dossier courant, pour que "python debug_cohort.py"
# fonctionne quel que soit l'endroit d'ou la commande est lancee.
DONNEES_TEST = Path(__file__).resolve().parent.parent / "tests" / "data" / "debug_cohort_data.csv"


# -----------------------------------------------------------------------------
# Dependance : robust_zscore (copiee telle quelle depuis le script principal)
# -----------------------------------------------------------------------------
def robust_zscore(values: pd.Series) -> pd.Series:
    x = pd.to_numeric(values, errors="coerce")
    med = x.median()
    mad = (x - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return pd.Series(np.zeros(len(x)), index=x.index, dtype=float)
    return 0.6745 * (x - med) / mad


# -----------------------------------------------------------------------------
# La fonction a deboguer (copie exacte, bugs compris, depuis le script principal)
# -----------------------------------------------------------------------------
def cohort_stats_and_peers_nv(df, rule_params):
    """
    UPDATE_AC_V1 :
    Calcule les statistiques de cohorte pour le calcul du z-score robuste et la détection des anomalies par cohorte.
    Intègre un élargissement ciblé : seules les petites cohortes sont élargies à chaque étape.
    """
    step = 0
    default_steps = [
        "Grade|Job_Family|Anciennete_Bucket",
        "Grade|Job_Family",
        "Grade"
    ]
    steps = rule_params.get("cohort_widening_steps", default_steps)
    min_size = rule_params.get("cohort_min_size", 5)

    def widen(step):
        step = min(step, len(steps) - 1)
        col_key = steps[step].split("|")
        key = df[col_key].astype(str).agg("|".join, axis=1)
        return col_key, key

    step = 0
    col_key, cohort_key = widen(step)
    df["Cohort_Key"] = cohort_key

    max_step = len(steps) - 1
    progress = True

    while progress and step < max_step:
        sizes = df.groupby("Cohort_Key")["Matricule"].transform("count")
        small_mask = sizes < min_size

        if not small_mask.any():
            break

        step += 1
        _, wider_key = widen(step)
        df.loc[small_mask, "Cohort_Key"] = wider_key[small_mask]

        sizes_new = df.groupby("Cohort_Key")["Matricule"].transform("count")
        progress = (sizes_new < min_size).any()

    df["Cohort_Size"] = df.groupby("Cohort_Key")["Matricule"].transform("count")

    cohort_stats = (
        df.groupby("Cohort_Key")
        .agg(
            Cohort_Median=("Fixe_Annuel_MAD", "median"),
            Cohort_Mean=("Fixe_Annuel_MAD", "mean"),
            Cohort_STD=("Fixe_Annuel_MAD", "std"),
            Cohort_P25=("Fixe_Annuel_MAD", lambda x: np.nanpercentile(x, 25)),
            Cohort_P75=("Fixe_Annuel_MAD", lambda x: np.nanpercentile(x, 75)),
            Cohort_Size=("Fixe_Annuel_MAD", "count")
        )
        .reset_index()
    )

    df = df.merge(cohort_stats, on="Cohort_Key", how="left")

    def robust_z(x):
        median = np.nanmedian(x)
        mad = np.nanmedian(np.abs(x - median))
        return 0 if mad == 0 else (x - median) / (1.4826 * mad)

    df["Cohort_ZScore"] = df.groupby("Cohort_Key")["Fixe_Annuel_MAD"].transform(robust_z)

    df["PeerZ"] = (
        df.groupby("Cohort_Key", group_keys=False)["Fixe_Annuel_MAD"]
          .apply(lambda x: robust_zscore(x))
          .reset_index(level=0, drop=True)
    )

    z_minor = float(rule_params.get("peer_z_threshold_minor", 2.0))
    z_major = float(rule_params.get("peer_z_threshold_major", 3.0))
    weights = rule_params.get("severity_weights", {})

    df["Peer_Flag"] = ""
    df["Rule_Flags"] = df.get("Rule_Flags", pd.Series([""] * len(df), index=df.index)).astype(str)

    minor_mask = df["PeerZ"].abs() >= z_minor
    major_mask = df["PeerZ"].abs() >= z_major

    df.loc[minor_mask, "Peer_Flag"] = "PEER_OUTLIER"
    df.loc[minor_mask, "Rule_Flags"] = df.loc[minor_mask, "Rule_Flags"].astype(str) + ";PEER_OUTLIER"

    df.loc[major_mask, "Rule_Score"] = df.loc[major_mask, "Rule_Score"].fillna(0) + weights.get("peer_outlier", 15)
    df.loc[major_mask, "Reason_Principale"] = (
        (df.loc[major_mask, "Reason_Principale"].fillna("").astype(str) + " & " +
         ("Outlier vs pairs (|Z|> ou = {:.1f})".format(z_major))).str.strip(" & ")
    )

    return df


# -----------------------------------------------------------------------------
# Jeu de donnees de test : charge depuis debug_cohort_data.csv (meme dossier)
# -----------------------------------------------------------------------------
def load_test_df():
    df = pd.read_csv(DONNEES_TEST)
    df["Rule_Flags"] = df["Rule_Flags"].fillna("")
    df["Reason_Principale"] = df["Reason_Principale"].fillna("")
    return df


if __name__ == "__main__":
    df_test = load_test_df()

    # Paramètres vides : utiliser les valeurs par défaut pour cet exemple de débogage.
    result = cohort_stats_and_peers_nv(df_test, rule_params={})
