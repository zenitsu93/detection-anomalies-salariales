#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script de détection des incohérences de rémunération fixe (version personnalisée).

Cette version est adaptée pour les besoins spécifiques du client :

- Suppression de la colonne « Ville » des fichiers et de la logique de jointure. Le rattachement géographique se fait
  désormais au niveau du pays uniquement (ou s'appuie sur les seules colonnes grade/famille de poste si aucune
  information géographique pertinente n'est disponible).
- Suppression de tout doublon de colonne « Matricule » présent dans le fichier des employés. Seule la première
  occurrence est conservée.
- Intégration de nouveaux champs RH (niveau de compétences N‑1, positionnement 9Box et indicateur hot job) dans
  l'analyse et dans la détection d'anomalies. Ces variables sont prises en compte par le modèle statistique.
- Possibilité de générer un fichier d'analyse des écarts de rémunération par sexe (optionnel).
- Mise en forme des colonnes numériques avec séparateur de milliers pour améliorer la lisibilité du fichier de sortie.

En entrée, les fichiers CSV doivent être encodés en cp1252 et utiliser un séparateur point‑virgule (« ; »).
Le fichier de règles YAML doit contenir les paramètres de détection (poids, seuils, etc.).

Utilisation :

```
py detect_salary_anomalies_custom.py --employees employes.csv --bands bands.csv --market market.csv --rulebook rulebook.yaml --output anomalies.csv [--excel-output anomalies.xlsx] [--gender-output gender_gap_analysis.csv]

python detect_salary_anomalies_custom.py \
  --employees chemin/vers/employes.csv \
  --bands chemin/vers/bands.csv \
  --market chemin/vers/market.csv \
  --rulebook chemin/vers/rulebook.yaml \
  --output chemin/vers/anomalies.csv \
  [--excel-output chemin/vers/anomalies.xlsx] \
  [--gender-output chemin/vers/gender_gap_analysis.csv]
```

La structure des colonnes d'entrée est décrite dans les fichiers « STRUCTURE EMP.csv », « STRUCTURE BANDS.csv »
et « STRUCTURE MARKET.csv » fournis par le client.

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

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.formatting.rule import ColorScaleRule

except ImportError as e:
    raise SystemExit("openpyxl est requis pour l'export Excel. Installez-le via: pip install openpyxl") from e

# -----------------------------------------------------------------------------
# Fonctions utilitaires
# -----------------------------------------------------------------------------

def robust_zscore(values: pd.Series) -> pd.Series:
    """Calcule un z-score robuste basé sur la médiane et l'écart absolu médian (MAD).

    Cette version est insensible aux valeurs extrêmes et s'utilise pour détecter
    des outliers dans les salaires au sein d'une cohorte.

    Args:
        values: série numérique.

    Returns:
        Série de z-scores robustes (float).
    """
    x = pd.to_numeric(values, errors="coerce")
    med = x.median()
    mad = (x - med).abs().median()
    if mad == 0 or np.isnan(mad):
        # Pourquoi (correction) : quand plus de la moitié d'un groupe a exactement le même salaire
        # (fréquent avec des grilles), l'écart médian (MAD) vaut 0. L'ancien code renvoyait alors 0
        # pour tout le monde : un salaire très différent des autres n'était jamais repéré. On se
        # rabat maintenant sur l'écart-type classique.
        std = x.std()
        if pd.notna(std) and std > 0:
            return (x - x.mean()) / std
        return pd.Series(0.0, index=x.index)
    return 0.6745 * (x - med) / mad


# -----------------------------------------------------------------------------
# Anciennete bucketing
#
# Pour pouvoir intégrer l'ancienneté dans la définition des cohortes, on crée
# une fonction qui transforme une valeur numérique d'ancienneté en une tranche
# textuelle. Les bornes proposées sont 0–2 ans, 3–5 ans, 6–10 ans et >10 ans.
def bucket_anciennete(x: object) -> str:
    """Regroupe l'ancienneté en tranches standardisées.

    Args:
        x: valeur d'ancienneté (en années) ou convertible en float.

    Returns:
        Chaîne représentant la tranche d'ancienneté. Retourne "NA" si
        l'ancienneté n'est pas disponible ou convertible.
    """
    try:
        val = float(x)
    except Exception:
        return "NA"
    if val <= 2:
        return "0-2"
    if val <= 5:
        return "3-5"
    if val <= 12:
        return "6-12"
    if val <= 20:
        return "13-20"
    return ">20"

def remove_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Supprime les colonnes dupliquées en ne conservant que la première occurrence.

    Lorsque pandas lit un CSV avec des en-têtes dupliqués, il crée des noms identiques. Cette fonction
    supprime les duplicats afin d'éviter d'avoir deux colonnes « Matricule » ou similaires.
    """
    if df.columns.duplicated().any():
        return df.loc[:, ~df.columns.duplicated()]
    return df


def compute_features(employees: pd.DataFrame, bands: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Calcule les ratios internes et externes nécessaires à l'analyse.

    Cette version prépare la tranche d'ancienneté pour chaque collaborateur (``Anciennete_Bucket``)
    et rattache les employés à leurs bandes internes via ``Job_Family`` et ``Grade`` uniquement.
    Après la jointure, les ratios internes et externes sont calculés.

    Args:
        employees: DataFrame contenant les informations des employés.
        bands: DataFrame des fourchettes de rémunération internes.
        market: DataFrame du benchmark marché (optionnel).

    Returns:
        DataFrame enrichi des colonnes Min, Mid, Max, Market_Median (si disponible) et des ratios calculés.
    """

    # Création du bucket d'ancienneté
    if "Anciennete" in employees.columns:
        employees["Anciennete_Bucket"] = employees["Anciennete"].apply(bucket_anciennete)
    else:
        employees["Anciennete_Bucket"] = "NA"

    # (Ce commentaire précisait "on ignore désormais le pays" : la colonne Pays est maintenant
    # retirée dès le chargement des fichiers, la précision n'avait plus lieu d'être ici.)
    # Clés de jointure
    ref_cols = []
    if "Job_Family" in employees.columns and "Job_Family" in bands.columns:
        ref_cols.append("Job_Family")
    if "Grade" in employees.columns and "Grade" in bands.columns:
        ref_cols.append("Grade")
    if not ref_cols:
        raise KeyError("Les colonnes 'Job_Family' et/ou 'Grade' manquent pour effectuer la jointure.")
    # Pourquoi (correction) : l'ancien contrôle ne gardait Min/Mid/Max que s'ils étaient DÉJÀ
    # présents dans le fichier des fourchettes : il ne pouvait donc jamais signaler qu'une de ces
    # colonnes manquait, et le script plantait plus loin avec une erreur peu claire. Il vérifie
    # maintenant vraiment les trois colonnes et affiche un message explicite.
    required_band_cols = ["Min", "Mid", "Max"]
    missing_cols = [c for c in required_band_cols if c not in bands.columns]
    if missing_cols:
        raise KeyError(f"[BANDS] Colonnes manquantes: {', '.join(missing_cols)}. Vérifiez votre fichier de fourchettes.")
    need_cols = ref_cols + required_band_cols

    bands_ref = bands[need_cols]
    # Pourquoi : si la grille contenait deux fois la même famille + grade, la jointure dupliquait
    # les employés concernés (ils apparaissaient deux fois dans les résultats et les totaux).
    # On ne garde plus que la première ligne et on prévient l'utilisateur.
    dup_bands_mask = bands_ref.duplicated(subset=ref_cols)
    if dup_bands_mask.any():
        print(
            f"[WARN] {int(dup_bands_mask.sum())} ligne(s) dupliquée(s) dans bands pour {ref_cols} - "
            "seule la première occurrence est conservée pour éviter de dupliquer les employés lors de la jointure.",
            file=sys.stderr,
        )
        bands_ref = bands_ref.drop_duplicates(subset=ref_cols, keep="first")

    n_before = len(employees)
    merged = employees.merge(bands_ref, on=ref_cols, how="left")
    if len(merged) != n_before:
        print(
            f"[WARN] La jointure avec bands a changé le nombre de lignes ({n_before} -> {len(merged)}); "
            "vérifiez l'unicité de Job_Family/Grade dans bands.",
            file=sys.stderr,
        )

    # Pourquoi : un employé dont la famille/grade n'existe pas dans la grille n'avait aucun ratio
    # interne, sans que personne ne soit prévenu. On le signale désormais.
    unmatched = merged["Mid"].isna() if "Mid" in merged.columns else pd.Series(False, index=merged.index)
    if unmatched.any():
        print(
            f"[WARN] {int(unmatched.sum())} employé(s) sans correspondance dans bands pour {ref_cols} "
            "ou avec Mid manquant - les ratios internes peuvent être indisponibles ; "
            "les comparaisons marché et pairs restent possibles si leurs données sont présentes.",
            file=sys.stderr,
        )

    if market is not None and "Median" in market.columns:
        market_cols = ref_cols + ["Median"]
        market_ref = market[market_cols].rename(columns={"Median": "Market_Median"})
        # Pourquoi : même problème que pour la grille interne (employés dupliqués par la jointure).
        dup_market_mask = market_ref.duplicated(subset=ref_cols)
        if dup_market_mask.any():
            print(
                f"[WARN] {int(dup_market_mask.sum())} ligne(s) dupliquée(s) dans market pour {ref_cols} - "
                "seule la première occurrence est conservée pour éviter de dupliquer les employés.",
                file=sys.stderr,
            )
            market_ref = market_ref.drop_duplicates(subset=ref_cols, keep="first")

        n_before_m = len(merged)
        merged = merged.merge(market_ref, on=ref_cols, how="left")
        if len(merged) != n_before_m:
            print(
                f"[WARN] La jointure avec market a changé le nombre de lignes ({n_before_m} -> {len(merged)}); "
                "vérifiez l'unicité de Job_Family/Grade dans market.",
                file=sys.stderr,
            )

    # Pourquoi (correction) : l'ancien nettoyage des montants supprimait tous les points (".").
    # Un salaire écrit "12345.67" devenait donc 1234567, soit 100 fois trop. Les montants sont
    # maintenant convertis directement en nombres, sans toucher au point décimal.
    amount_cols = [c for c in ["Fixe_Annuel_MAD", "Min", "Mid", "Max", "Market_Median"] if c in merged.columns]
    for _col in amount_cols:
        if not pd.api.types.is_numeric_dtype(merged[_col]):
            # Pourquoi : une valeur illisible (ex. "abc") devenait vide sans aucun message. On compte
            # maintenant ces valeurs et on les signale, pour que le fichier puisse être corrigé.
            n_bad = merged[_col].notna().sum() - pd.to_numeric(merged[_col], errors="coerce").notna().sum()
            if n_bad > 0:
                print(
                    f"[WARN] {int(n_bad)} valeur(s) non numérique(s) dans la colonne '{_col}' - "
                    "traitées comme manquantes (NaN).",
                    file=sys.stderr,
                )
            merged[_col] = pd.to_numeric(merged[_col], errors="coerce")

    # Calcul des ratios
    # Pourquoi (correction) : un Mid (ou une médiane marché) à 0 provoquait une division par zéro
    # et un ratio "infini" qui faussait les règles. Un 0 est maintenant traité comme une valeur
    # manquante : le ratio reste vide.
    mid_safe = merged["Mid"].replace(0, np.nan)
    merged["CompaRatio"] = merged["Fixe_Annuel_MAD"] / mid_safe
    rng = (merged["Max"] - merged["Min"]).replace(0, np.nan)
    merged["RangePenetration"] = (merged["Fixe_Annuel_MAD"] - merged["Min"]) / rng

    if "Market_Median" in merged.columns:
        market_safe = merged["Market_Median"].replace(0, np.nan)
        merged["MarketRatio"] = merged["Fixe_Annuel_MAD"] / market_safe
    else:
        merged["MarketRatio"] = np.nan

    return merged



def apply_rulebook(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Applique les règles déterministes du rulebook sur chaque ligne du DataFrame.

    Les poids et seuils sont définis dans le fichier YAML fourni. À chaque règle déclenchée, un flag
    est ajouté dans la colonne Rule_Flags et la colonne Rule_Score est incrémentée du poids correspondant.
    """
    weights = rule_params.get("severity_weights", {})
    low_buf = rule_params.get("range_penetration_low_buffer", -0.05)
    high_buf = rule_params.get("range_penetration_high_buffer", 0.05)
    compa_lo = rule_params.get("compa_ratio_low", 0.85)
    compa_hi = rule_params.get("compa_ratio_high", 1.15)
    market_lo = rule_params.get("market_low", 0.90)
    market_hi = rule_params.get("market_high", 1.20)

    df["Rule_Flags"] = ""
    df["Rule_Score"] = 0.0
    df["Reason_Principale"] = ""

    # Règles hors-bande (range penetration)
    cond_low = df["RangePenetration"] < low_buf
    cond_high = df["RangePenetration"] > (1 + high_buf)
    out_of_band = cond_low | cond_high
    df.loc[out_of_band, "Rule_Flags"] = df["Rule_Flags"] + ";OUT_OF_BAND"
    df.loc[out_of_band, "Rule_Score"] += weights.get("out_of_band", 30)

    # Règles compa ratio
    compa_low_flag = df["CompaRatio"] < compa_lo
    compa_high_flag = df["CompaRatio"] > compa_hi
    compa_flag = compa_low_flag | compa_high_flag
    df.loc[compa_flag, "Rule_Flags"] = df["Rule_Flags"] + ";COMPA_RATIO"
    df.loc[compa_flag, "Rule_Score"] += weights.get("compa_ratio", 20)

    # Règles marché
    market_low_flag = df["MarketRatio"] < market_lo
    market_high_flag = df["MarketRatio"] > market_hi
    has_market = df["MarketRatio"].notna()
    mk_gap = (market_low_flag | market_high_flag) & has_market
    df.loc[mk_gap, "Rule_Flags"] = df["Rule_Flags"] + ";MARKET_GAP"
    df.loc[mk_gap, "Rule_Score"] += weights.get("market_gap", 15)

    # Génération d'une raison principale lisible
    def reason(row):
        motifs = []
        if row["RangePenetration"] < low_buf:
            motifs.append("Salaire sous MIN interne")
        elif row["RangePenetration"] > (1 + high_buf):
            motifs.append("Salaire au-dessus du MAX interne")
        if row["CompaRatio"] < compa_lo:
            motifs.append(f"CompaRatio={row['CompaRatio']:.2f} (<{compa_lo})")
        elif row["CompaRatio"] > compa_hi:
            motifs.append(f"CompaRatio={row['CompaRatio']:.2f} (>{compa_hi})")
        if pd.notna(row.get("MarketRatio", np.nan)):
            if row["MarketRatio"] < market_lo:
                motifs.append("Sous la mediane marche")
            elif row["MarketRatio"] > market_hi:
                motifs.append("Au-dessus de la mediane marche")
        return " & ".join(motifs) if motifs else ""

    df["Reason_Principale"] = df.apply(reason, axis=1)
    return df

def cohort_stats_and_peers_nv(df, rule_params):
    """Calcule les statistiques de cohorte pour le calcul du z-score robuste et la détection des anomalies par cohorte.

    Intègre un élargissement ciblé : seules les petites cohortes sont élargies à chaque étape.
    """
    # Définir les étapes d'élargissement.
    # On inclut l'ancienneté (via Anciennete_Bucket) dans la définition des cohortes.
    # La première étape utilise Grade × Job_Family × tranche d'ancienneté ;
    # puis on élargit à Grade × Job_Family puis uniquement au grade si la cohorte est trop petite.
    default_steps = [
        "Grade|Job_Family|Anciennete_Bucket",
        "Grade|Job_Family",
        "Grade"
    ]
    steps = rule_params.get("cohort_widening_steps", default_steps)
    min_size = rule_params.get("cohort_min_size", 5)

    # --- Construction initiale de la cohorte ---
    def widen(step):
        step = min(step, len(steps) - 1)
        col_key = steps[step].split("|")
        key = df[col_key].astype(str).agg("|".join, axis=1)
        return col_key, key

    step = 0
    _, cohort_key = widen(step)
    df["Cohort_Key"] = cohort_key

    max_step = len(steps) - 1
    progress = True

    # --- Boucle d'élargissement ciblé ---
    while progress and step < max_step:
        sizes = df.groupby("Cohort_Key")["Matricule"].transform("count")
        small_mask = sizes < min_size

        if not small_mask.any():
            break  # plus aucune petite cohorte, on sort

        step += 1
        _, wider_key = widen(step)

        # Élargissement ciblé : on ne change la clé que pour les cohortes trop petites
        df.loc[small_mask, "Cohort_Key"] = wider_key[small_mask]

        # Vérifie si des petites cohortes subsistent
        sizes_new = df.groupby("Cohort_Key")["Matricule"].transform("count")
        progress = (sizes_new < min_size).any()

    # --- Taille finale des cohortes ---
    df["Cohort_Size"] = df.groupby("Cohort_Key")["Matricule"].transform("count")

    # --- Statistiques de cohorte ---
    cohort_stats = (
        df.groupby("Cohort_Key")
        .agg(
            Cohort_Median=("Fixe_Annuel_MAD", "median"),
            Cohort_Mean=("Fixe_Annuel_MAD", "mean"),
            Cohort_STD=("Fixe_Annuel_MAD", "std"),
            Cohort_P25=("Fixe_Annuel_MAD", lambda x: np.nanpercentile(x, 25)),
            Cohort_P75=("Fixe_Annuel_MAD", lambda x: np.nanpercentile(x, 75)),
        )
        .reset_index()
    )

    # Pourquoi Cohort_Size n'est plus recalculée dans cohort_stats : elle existe déjà (plus haut).
    # La recalculer créait deux colonnes en double à la fusion (Cohort_Size_x / Cohort_Size_y).
    # L'indicateur "Cohort_ZScore", calculé mais jamais utilisé, a aussi été retiré.
    df = df.merge(cohort_stats, on="Cohort_Key", how="left")

    # --- Peer-level robust z-score (per-cohort peers) and peer outlier flags ---
    # compute PeerZ using the main robust_zscore helper so the behavior matches
    df["PeerZ"] = (
        df.groupby("Cohort_Key", group_keys=False)["Fixe_Annuel_MAD"]
          .apply(lambda x: robust_zscore(x))
          .reset_index(level=0, drop=True)
    )

    # thresholds and weights
    z_minor = float(rule_params.get("peer_z_threshold_minor", 2.0))
    z_major = float(rule_params.get("peer_z_threshold_major", 3.0))
    weights = rule_params.get("severity_weights", {})

    # init/ensure fields
    df["Peer_Flag"] = ""
    df["Rule_Flags"] = df.get("Rule_Flags", pd.Series([""] * len(df), index=df.index)).astype(str)

    minor_mask = df["PeerZ"].abs() >= z_minor
    major_mask = df["PeerZ"].abs() >= z_major

    # z_minor: only set flags
    df.loc[minor_mask, "Peer_Flag"] = "PEER_OUTLIER"
    df.loc[minor_mask, "Rule_Flags"] = df.loc[minor_mask, "Rule_Flags"].astype(str) + ";PEER_OUTLIER"

    # z_major: increment score (important) and add principal reason
    df.loc[major_mask, "Rule_Score"] = df.loc[major_mask, "Rule_Score"].fillna(0) + weights.get("peer_outlier", 15)
    df.loc[major_mask, "Reason_Principale"] = (
        (df.loc[major_mask, "Reason_Principale"].fillna("").astype(str) + " & " +
         ("Outlier vs pairs (|Z|> ou = {:.1f})".format(z_major))).str.strip(" & ")
    )

    return df

 



def ml_anomaly(df: pd.DataFrame, rule_params: dict, random_state: int = 42) -> pd.DataFrame:
    """Calcule un score d'anomalie non supervisé via IsolationForest.

    Les variables utilisées incluent désormais les nouvelles caractéristiques RH (niveau de compétences N‑1,
    positionnement 9Box et hot job) lorsque celles‑ci sont présentes. Les valeurs manquantes sont remplacées
    par la médiane de chaque colonne.

    contamination (proportion d'anomalies attendue) et n_estimators étaient auparavant codés en dur
    (0.05 / 200) alors que tous les autres seuils du script se règlent via le rulebook YAML sans
    toucher au code. Ils sont désormais lus dans rule_params, avec ces mêmes valeurs par défaut :
    le comportement ne change pas tant que le rulebook ne définit pas ml_contamination/ml_n_estimators.
    """
    # Liste des colonnes numériques potentielles
    base_feats = ["Fixe_Annuel_MAD", "CompaRatio", "RangePenetration", "MarketRatio", "Age", "Anciennete"]
    extra_feats = [c for c in ["Competence_N1", "Positionnement_9BOX", "Hot_job"] if c in df.columns]
    feats = base_feats + extra_feats
    # Une colonne entièrement vide (ex: MarketRatio sans --market) n'a pas de médiane : l'imputation
    # ne comble rien et laisse du NaN jusque dans l'IsolationForest. On exclut ces colonnes plutôt
    # que de les imputer dans le vide.
    feats = [c for c in feats if pd.to_numeric(df[c], errors="coerce").notna().any()]
    X = df[feats].copy()
    for c in feats:
        # La médiane d'imputation doit être calculée sur la série déjà convertie en numérique,
        # sinon elle porte sur les valeurs brutes (potentiellement non numériques) de la colonne.
        coerced = pd.to_numeric(X[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        X[c] = coerced.fillna(coerced.median())

    # Standardisation conservée dans la préparation. Aucun gain de détection n'est
    # établi ici par cette transformation seule.
    X_scaled = StandardScaler().fit_transform(X)

    contamination = float(rule_params.get("ml_contamination", 0.05))
    n_estimators = int(rule_params.get("ml_n_estimators", 200))
    iso = IsolationForest(n_estimators=n_estimators, contamination=contamination, random_state=random_state)
    iso.fit(X_scaled)
    score = -iso.score_samples(X_scaled)
    s_min, s_max = float(score.min()), float(score.max())
    if s_max > s_min:
        score_norm = 100 * (score - s_min) / (s_max - s_min)
        # L'element au score maximal devrait valoir exactement 100 (ratio = 1), mais l'arrondi en
        # virgule flottante peut donner une valeur infime au-dessus (ex: 100.00000000000001) :
        # sans consequence pratique (l'export CSV/Excel arrondit a 2 decimales), mais on la
        # ramene dans l'intervalle annonce [0, 100] pour que ce soit vrai exactement, pas
        # seulement "vrai a l'epsilon flottant pres".
        score_norm = np.clip(score_norm, 0, 100)
    else:
        score_norm = 50.0
    df["ML_AnomalyScore"] = score_norm
    return df



def aggregate_risk(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Agrège le score de règles et le score d'IA pour produire un score de risque global.

    Le poids attribué à chaque composante est configurable via le rulebook (defaults : 0,7 pour les règles et 0,3
    pour l'IA). La sévérité est ensuite dérivée selon des seuils définis dans le rulebook.
    """
    rule_w = float(rule_params.get("rule_weight", 0.7))
    ml_w = float(rule_params.get("ml_weight", 0.3))
    df["RiskScore"] = (rule_w * df["Rule_Score"].fillna(0)) + (ml_w * df["ML_AnomalyScore"].fillna(0))

    # Définition des buckets (prioritisation)
    buckets = rule_params.get("prioritization_buckets", {
        "Critical": [70, 100],
        "Major": [50, 69],
        "Minor": [30, 49],
        "Info": [0, 29]
    })

    # Les bornes "hi" (ex: Major va jusqu'a 69, Critical commence a 70) laissaient un trou entre
    # deux categories des que RiskScore n'est pas un nombre entier (ex: 69.9 ou 49.9), ce qui est
    # le cas courant puisque RiskScore est une moyenne ponderee de scores continus. Un score de
    # 69.9 ne satisfaisait ni "x <= 69" (Major) ni "x >= 70" (Critical) : il retombait dans le cas
    # par defaut "Info", la categorie la MOINS grave, alors qu'il aurait du etre classe "Major".
    # Sur un fichier de plusieurs milliers de salaries, ce trou (large d'environ 1 point a chaque
    # frontiere) reclassait ainsi en "Info" un nombre non negligeable de cas pourtant a surveiller.
    #
    # Correction : on cherche desormais la categorie dont la borne basse ("lo") est la plus haute
    # tout en restant <= au score, en parcourant les categories de la plus severe a la moins
    # severe. Les bornes hautes ne servent plus qu'a titre indicatif dans le rulebook ; il n'y a
    # ainsi plus aucun trou possible entre deux categories.
    categories_par_severite_decroissante = sorted(buckets.items(), key=lambda item: item[1][0], reverse=True)

    def sev(x):
        for name, (lo, _hi) in categories_par_severite_decroissante:
            if x >= lo:
                return name
        return "Info"
    df["Severity"] = df["RiskScore"].apply(sev)
    return df



def recommendations(df: pd.DataFrame) -> pd.DataFrame:
    """Génère des recommandations d'action et le coût d'ajustement pour chaque ligne.

    Les recommandations sont basées sur la fourchette interne (Min/Mid/Max) et la position actuelle du salarié.
    """
    reco = []
    cost = []
    for _, row in df.iterrows():
        fix = row.get("Fixe_Annuel_MAD", np.nan)
        mn, md, mx = row.get("Min", np.nan), row.get("Mid", np.nan), row.get("Max", np.nan)
        compa = row.get("CompaRatio", np.nan)

        msg = ""
        delta = 0.0
        if pd.notna(mn) and pd.notna(md) and pd.notna(mx) and pd.notna(fix):
            if fix < mn:
                msg = "Ajuster au MIN"
                delta = max(0.0, mn - fix)
            elif compa < 0.85 and fix < md:
                msg = "Ajuster vers MID"
                delta = max(0.0, md - fix)
            elif fix > mx:
                msg = "Au-dessus MAX: Revue"
                delta = 0.0
            elif compa > 1.15:
                msg = "Compa élevée: Revue"
                delta = 0.0
        reco.append(msg)
        cost.append(delta)
    df["Reco"] = reco
    df["Cout_Ajustement"] = cost
    return df


def to_excel_colored(df: pd.DataFrame, path_xlsx: str) -> None:
    """Exporte le DataFrame complet dans un fichier Excel avec onglets, filtres et coloration du RiskScore.

    Des feuilles séparées sont créées pour chaque niveau de sévérité, ainsi qu'un onglet de synthèse budgétaire.
    """
    import openpyxl
    from openpyxl.chart import PieChart, Reference
    path_xlsx = Path(path_xlsx)
    with pd.ExcelWriter(path_xlsx, engine="openpyxl") as xw:
        df_sorted = df.sort_values(["Severity", "RiskScore"], ascending=[True, False])
        df_sorted.to_excel(xw, sheet_name="All", index=False)
        for sev in ["Critical", "Major", "Minor", "Info"]:
            sub = df[df["Severity"] == sev].sort_values("RiskScore", ascending=False)
            if sub.empty:
                sub = df.head(0).copy()
            sub.to_excel(xw, sheet_name=sev, index=False)
        # Synthèse budgétaire (Cout_Ajustement par Entite_N1 et Severity)

        if "Cout_Ajustement" in df.columns:
            grp_cols = [c for c in ["Severity", "Entite_N1"] if c in df.columns]
            import locale
            try:
                locale.setlocale(locale.LC_ALL, '')
            except Exception:
                locale.setlocale(locale.LC_ALL, locale.getdefaultlocale()[0])
            df["Cout_Ajustement_num"] = pd.to_numeric(df["Cout_Ajustement"].str.replace(" ", ""), errors="coerce")
            synth = (df.groupby(grp_cols, dropna=False)["Cout_Ajustement_num"]
                     .sum()
                     .reset_index()
                     .sort_values(["Severity", "Cout_Ajustement_num"], ascending=[True, False]))
            # Add total row
            total = synth["Cout_Ajustement_num"].sum()
            if len(grp_cols) == 2:
                synth.loc[len(synth)] = ["TOTAL", "", total]
            else:
                synth.loc[len(synth)] = ["TOTAL", total]
            # Format numbers with locale
            if "Cout_Ajustement_num" in synth.columns:
                synth["Cout_Ajustement_num"] = synth["Cout_Ajustement_num"].apply(lambda x: locale.format_string('%.2f', x, grouping=True) if pd.notna(x) else "")
                synth = synth.rename(columns={"Cout_Ajustement_num": "Cout_Ajustement"})
            synth.to_excel(xw, sheet_name="Budget_Synthese", index=False)

        # Statistiques globales
        stats = {
            "Total anomalies": len(df),
            "Critical": (df["Severity"] == "Critical").sum(),
            "Major": (df["Severity"] == "Major").sum(),
            "Minor": (df["Severity"] == "Minor").sum(),
            "Info": (df["Severity"] == "Info").sum(),
            "Total adjustment cost": df["Cout_Ajustement"].apply(pd.to_numeric, errors="coerce").sum()
        }
        stats_df = pd.DataFrame(list(stats.items()), columns=["Metric", "Value"])
        stats_df.to_excel(xw, sheet_name="Statistics", index=False)

    wb = openpyxl.load_workbook(path_xlsx)
    # Formatting and charts
    for ws_name in ["All", "Critical", "Major", "Minor", "Info"]:
        if ws_name not in wb.sheetnames:
            continue
        ws = wb[ws_name]
        ws.freeze_panes = "A2"
        max_col = ws.max_column
        max_row = ws.max_row
        ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(max_col)}{max_row}"
        # Entêtes en gras et couleur de fond
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="FFF2F2F2", end_color="FFF2F2F2", fill_type="solid")
            cell.alignment = Alignment(vertical="center")
        header = [c.value for c in ws[1]]
        # Coloration conditionnelle sur RiskScore
        if "RiskScore" in header:
            col_idx = header.index("RiskScore") + 1
            rng = openpyxl.utils.get_column_letter(col_idx) + "2:" + openpyxl.utils.get_column_letter(col_idx) + str(max_row)
            rule = ColorScaleRule(start_type="num", start_value=0, start_color="63BE7B",
                                  mid_type="num", mid_value=50, mid_color="FFEB84",
                                  end_type="num", end_value=100, end_color="F8696B")
            ws.conditional_formatting.add(rng, rule)
        # Ajuster la largeur des colonnes
        for i, name in enumerate(header, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(40, max(12, len(str(name)) + 2))

    # Add only severity breakdown pie chart to Statistics sheet
    if "Statistics" in wb.sheetnames:
        ws = wb["Statistics"]
        pie = PieChart()
        pie.title = "Severity Breakdown"
        pie_data = Reference(ws, min_col=2, min_row=2, max_row=5)
        pie_labels = Reference(ws, min_col=1, min_row=2, max_row=5)
        pie.add_data(pie_data, titles_from_data=False)
        pie.set_categories(pie_labels)
        ws.add_chart(pie, "D2")
    wb.save(path_xlsx)




def format_numeric_fields(out: pd.DataFrame) -> pd.DataFrame:
    """Formate les colonnes numériques selon la locale utilisateur (Windows)."""
    import locale
    try:
        locale.setlocale(locale.LC_ALL, '')
    except Exception:
        locale.setlocale(locale.LC_ALL, locale.getdefaultlocale()[0])
    def fmt(x):
        if pd.isna(x):
            return ""
        try:
            return locale.format_string('%.2f', float(x), grouping=True)
        except Exception:
            return str(x)
    num_cols = ["Fixe_Annuel_MAD", "Min", "Mid", "Max", "Market_Median", "Cout_Ajustement"]
    for col in num_cols:
        if col in out.columns:
            out[col] = out[col].apply(fmt)
    return out




def gender_gap_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Analyse les écarts de rémunération par sexe et par groupe de comparaison.

    Le résultat contient, pour chaque combinaison de Job_Family et Grade (si présents), la médiane des salaires fixes
    pour les personnes identifiées comme "F" et "M" dans la colonne Sexe, ainsi qu'un ratio M/F permettant de
    visualiser le gap (valeur > 1 signifie que la médiane masculine est supérieure à la médiane féminine).
    """
    # S'assurer de disposer des colonnes nécessaires
    if "Sexe" not in df.columns:
        raise ValueError("La colonne Sexe est requise pour réaliser l'analyse des écarts de rémunération par sexe.")
    group_cols = []
    if "Job_Family" in df.columns:
        group_cols.append("Job_Family")
    if "Grade" in df.columns:
        group_cols.append("Grade")
    # Calcul des médianes
    med = df.groupby(group_cols + ["Sexe"])["Fixe_Annuel_MAD"].median().unstack()
    # Renommage des colonnes sexe pour plus de clarté
    med = med.rename(columns=lambda x: f"Median_{str(x)}")
    # Calcul du ratio (si les deux sexes sont présents)
    if "Median_M" in med.columns and "Median_F" in med.columns:
        med["M_div_F"] = med["Median_M"] / med["Median_F"]
    elif "Median_M" in med.columns:
        med["M_div_F"] = np.nan
    elif "Median_F" in med.columns:
        med["M_div_F"] = np.nan
    med = med.reset_index()
    return med


def _read_csv_guess_sep(path: str) -> pd.DataFrame:
    """Tente de lire un fichier CSV en détectant automatiquement le séparateur.

    On tente successivement la virgule puis le point-virgule. Si le résultat
    comporte plus d'une colonne, on le retourne. À défaut, pandas détecte
    automatiquement le séparateur.

    Args:
        path: chemin vers le fichier CSV.

    Returns:
        DataFrame lu depuis le CSV.
    """
    for sep in [",", ";"]:
        try:
            df = pd.read_csv(path, sep=sep, encoding="cp1252", engine="python")
            # S'il y a plus d'une colonne, on considère que le séparateur est correct
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    # Dernier recours : détecter automatiquement
    return pd.read_csv(path, sep=None, encoding="cp1252", engine="python")


EXPECTED_RULE_KEYS = {
    "severity_weights": {
        "out_of_band": 30,
        "compa_ratio": 20,
        "market_gap": 15,
        "peer_outlier": 15,
        "ml_strong_signal": 15,
    },
    "ml_strong_signal_percentile": 0.95,
    "ml_contamination": 0.05,
    "ml_n_estimators": 200,
    "range_penetration_low_buffer": -0.05,
    "range_penetration_high_buffer": 0.05,
    "compa_ratio_low": 0.85,
    "compa_ratio_high": 1.15,
    "market_low": 0.90,
    "market_high": 1.20,
    "cohort_min_size": 5,
    "cohort_widening_steps": ["Grade|Job_Family|Anciennete_Bucket", "Grade|Job_Family", "Grade"],
    "peer_z_threshold_minor": 2.0,
    "peer_z_threshold_major": 3.0,
    "rule_weight": 0.7,
    "ml_weight": 0.3,
    "prioritization_buckets": {"Critical": [70, 100], "Major": [50, 69], "Minor": [30, 49], "Info": [0, 29]},
}


def validate_rule_params(rule_params: dict) -> None:
    """Vérifie que les clés attendues sous ``rules:`` sont présentes dans le rulebook chargé et
    avertit explicitement (stderr) pour chacune de celles qui manquent.

    Le script continue de fonctionner avec les valeurs par défaut (comportement inchangé), mais
    un rulebook mal structuré ou obsolète ne doit plus passer inaperçu : avant cette vérification,
    une clé absente ou mal nommée était silencieusement remplacée par un défaut, sans aucun signal.
    """
    for key, default in EXPECTED_RULE_KEYS.items():
        if key not in rule_params:
            print(f"[WARN][RULEBOOK] Clé 'rules.{key}' absente - valeur par défaut utilisée: {default}", file=sys.stderr)
            continue
        if isinstance(default, dict):
            sub_params = rule_params.get(key) or {}
            for sub_key, sub_default in default.items():
                if sub_key not in sub_params:
                    print(
                        f"[WARN][RULEBOOK] Clé 'rules.{key}.{sub_key}' absente - valeur par défaut utilisée: {sub_default}",
                        file=sys.stderr,
                    )



def apply_ml_strong_signal(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Fait remonter un signal ML très fort dans Rule_Score même quand aucune règle déterministe
    ne s'est déclenchée, pour les cas où le salaire est conforme à la bande/aux pairs mais où
    l'IsolationForest détecte une combinaison de facteurs inhabituelle (ex: âge/ancienneté très
    atypique pour le grade). Sans ce correctif, un tel cas peut atteindre un score ML proche du
    maximum (mesuré à 89/100 en test) et rester malgré tout classé "Info" une fois agrégé avec
    rule_weight/ml_weight (0.7/0.3 par défaut)

    Le seuil est un percentile du score ML DE CE RUN (et non une valeur absolue) car
    ML_AnomalyScore est renormalisé en 0-100 à chaque exécution (min-max sur le lot traité) : un
    seuil absolu n'aurait pas le même sens d'un jeu de données à l'autre.
    """
    weights = rule_params.get("severity_weights", {})
    percentile = float(rule_params.get("ml_strong_signal_percentile", 0.95))
    if df["ML_AnomalyScore"].notna().sum() < 20:
        return df  # percentile peu significatif sur un trop petit échantillon

    cutoff = df["ML_AnomalyScore"].quantile(percentile)
    no_rule_flag = df["Rule_Flags"].astype(str).str.len() == 0
    strong_ml = (df["ML_AnomalyScore"] >= cutoff) & no_rule_flag

    if not strong_ml.any():
        return df

    df.loc[strong_ml, "Rule_Flags"] = df.loc[strong_ml, "Rule_Flags"].astype(str) + ";ML_STRONG_SIGNAL"
    df.loc[strong_ml, "Rule_Score"] = (
        df.loc[strong_ml, "Rule_Score"].fillna(0) + weights.get("ml_strong_signal", 15)
    )
    has_reason = df["Reason_Principale"].astype(str).str.len() > 0
    sep = pd.Series(" & ", index=df.index).where(has_reason, "")
    df.loc[strong_ml, "Reason_Principale"] = (
        df.loc[strong_ml, "Reason_Principale"].astype(str)
        + sep[strong_ml]
        + "Profil atypique détecté par le modèle ML (aucune règle de salaire déclenchée)"
    )
    return df



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
    emp = _read_csv_guess_sep(args.employees)
    bands = _read_csv_guess_sep(args.bands)
    market = _read_csv_guess_sep(args.market) if args.market else None

    # Suppression des colonnes dupliquées sur les employés (ex: double colonne Matricule)
    emp = remove_duplicate_columns(emp)
    # Pourquoi (correction) : l'ancienne étape de renommage des colonnes (standardize_all) utilisait
    # des dictionnaires désactivés (placés entre guillemets), ce qui faisait planter le script. Elle a
    # été retirée : les fichiers utilisent déjà les bons noms de colonnes. À la place, on retire
    # seulement la colonne Pays, identique pour tout le monde.
    # Le périmètre couvre un seul pays : aucune clé géographique supplémentaire.
    for table in (emp, bands, market):
        if table is not None and "Pays" in table.columns:
            table.drop(columns=["Pays"], inplace=True)

    # Lecture du rulebook
    with open(args.rulebook, "r", encoding="utf-8") as f:
        rulebook = yaml.safe_load(f) or {}
    rule_params = rulebook.get("rules", {})
    # Pourquoi : avant, un paramètre absent ou mal nommé dans le fichier de règles était remplacé
    # en silence par une valeur par défaut. On affiche maintenant un avertissement pour chacun.
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