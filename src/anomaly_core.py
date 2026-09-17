#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Logique de detection des incoherences de remuneration fixe.

Ce fichier regroupe tout ce qui touche au calcul lui-meme : les ratios internes/marche, les
regles deterministes du rulebook, les statistiques de cohorte et le z-score robuste entre pairs,
le score d'anomalie par intelligence artificielle (IsolationForest), l'agregation en un score de
risque global et les recommandations d'ajustement.

Rien ici ne lit un fichier CSV ni n'ecrit de fichier Excel : cette partie se trouve dans
anomaly_io.py. Ce fichier est importe par detect_salary_anomalies_custom_fixed.py, qui reste le
point d'entree en ligne de commande.

Ce decoupage en plusieurs fichiers est une reorganisation du code pour le rendre plus facile a
relire et a maintenir : il ne change rien au comportement du script (memes calculs, memes
resultats). Voir corrections.txt et explication_simple.txt pour l'historique des corrections
apportees au fil des relectures precedentes.
"""

import sys

import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

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
        std = x.std()
        if pd.notna(std) and std > 0:
            return (x - x.mean()) / std
        return pd.Series(0.0, index=x.index).where(x.notna())
    return 0.6745 * (x - med) / mad




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
    if not np.isfinite(val) or val < 0:
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

    # Clés de jointure
    ref_cols = []
    if "Job_Family" in employees.columns and "Job_Family" in bands.columns:
        ref_cols.append("Job_Family")
    if "Grade" in employees.columns and "Grade" in bands.columns:
        ref_cols.append("Grade")
    if not ref_cols:
        raise KeyError("Les colonnes 'Job_Family' et/ou 'Grade' manquent pour effectuer la jointure.")
    required_band_cols = ["Min", "Mid", "Max"]
    missing_cols = [c for c in required_band_cols if c not in bands.columns]
    if missing_cols:
        raise KeyError(f"[BANDS] Colonnes manquantes: {', '.join(missing_cols)}. Vérifiez votre fichier de fourchettes.")
    need_cols = ref_cols + required_band_cols

    bands_ref = bands[need_cols]
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

    amount_cols = [c for c in ["Fixe_Annuel_MAD", "Min", "Mid", "Max", "Market_Median"] if c in merged.columns]
    for _col in amount_cols:
        if not pd.api.types.is_numeric_dtype(merged[_col]):
            n_bad = merged[_col].notna().sum() - pd.to_numeric(merged[_col], errors="coerce").notna().sum()
            if n_bad > 0:
                print(
                    f"[WARN] {int(n_bad)} valeur(s) non numérique(s) dans la colonne '{_col}' - "
                    "traitées comme manquantes (NaN).",
                    file=sys.stderr,
                )
            merged[_col] = pd.to_numeric(merged[_col], errors="coerce")

    # Calcul des ratios
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

    # Génération vectorisée de la raison principale (remplace l'ancien df.apply(axis=1),
    # coûteux en Python pur sur de gros volumes).
    def _add(reason_parts: pd.Series, mask: pd.Series, text) -> pd.Series:
        sep = pd.Series(" & ", index=df.index).where(reason_parts.str.len() > 0, "")
        return reason_parts.mask(mask, reason_parts + sep + text)

    reason_parts = pd.Series("", index=df.index, dtype=object)
    reason_parts = _add(reason_parts, cond_low, "Salaire sous MIN interne")
    reason_parts = _add(reason_parts, cond_high, "Salaire au-dessus du MAX interne")
    compa_txt_lo = "CompaRatio=" + df["CompaRatio"].round(2).astype(str) + f" (<{compa_lo})"
    compa_txt_hi = "CompaRatio=" + df["CompaRatio"].round(2).astype(str) + f" (>{compa_hi})"
    reason_parts = _add(reason_parts, compa_low_flag, compa_txt_lo)
    reason_parts = _add(reason_parts, compa_high_flag, compa_txt_hi)
    reason_parts = _add(reason_parts, market_low_flag & has_market, "Sous la mediane marche")
    reason_parts = _add(reason_parts, market_high_flag & has_market, "Au-dessus de la mediane marche")

    df["Reason_Principale"] = reason_parts
    return df




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
    if df["ML_AnomalyScore"].nunique() < 2:
        return df  # des scores identiques ne distinguent aucun profil atypique

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
    feats = [c for c in feats if c in df.columns
             and pd.to_numeric(df[c], errors="coerce").replace([np.inf, -np.inf], np.nan).notna().any()]
    if df.empty or not feats:
        print("[WARN] Aucune donnée numérique exploitable pour le modèle ML - score indisponible.", file=sys.stderr)
        df["ML_AnomalyScore"] = np.nan
        return df
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



def recommendations(df: pd.DataFrame, rule_params: dict = None) -> pd.DataFrame:
    """Génère des recommandations d'action et le coût d'ajustement pour chaque ligne.

    Les recommandations sont basées sur la fourchette interne (Min/Mid/Max) et la position actuelle du salarié.
    Version vectorisée (remplace l'ancienne boucle ``for _, row in df.iterrows()``).
    Les seuils CompaRatio suivent le même rulebook que la détection.
    """
    rule_params = rule_params or {}
    compa_lo = float(rule_params.get("compa_ratio_low", 0.85))
    compa_hi = float(rule_params.get("compa_ratio_high", 1.15))
    fix = pd.to_numeric(df.get("Fixe_Annuel_MAD"), errors="coerce")
    mn = pd.to_numeric(df.get("Min"), errors="coerce")
    md = pd.to_numeric(df.get("Mid"), errors="coerce")
    mx = pd.to_numeric(df.get("Max"), errors="coerce")
    compa = pd.to_numeric(df.get("CompaRatio"), errors="coerce")

    have_band = mn.notna() & md.notna() & mx.notna() & fix.notna()

    below_min = have_band & (fix < mn)
    to_mid = have_band & ~below_min & (compa < compa_lo) & (fix < md)
    above_max = have_band & ~below_min & ~to_mid & (fix > mx)
    high_compa = have_band & ~below_min & ~to_mid & ~above_max & (compa > compa_hi)

    df["Reco"] = np.select(
        [below_min, to_mid, above_max, high_compa],
        ["Ajuster au MIN", "Ajuster vers MID", "Au-dessus MAX: Revue", "Compa élevée: Revue"],
        default="",
    )
    df["Cout_Ajustement"] = np.select(
        [below_min, to_mid],
        [(mn - fix).clip(lower=0), (md - fix).clip(lower=0)],
        default=0.0,
    )
    return df





def gender_gap_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Analyse les écarts de rémunération par sexe et par groupe de comparaison.

    Le résultat contient, pour chaque combinaison de Job_Family et Grade (si présents), la médiane des salaires fixes
    pour les personnes identifiées comme "F" et "M" dans la colonne Sexe, ainsi qu'un ratio M/F permettant de
    visualiser le gap (valeur > 1 signifie que la médiane masculine est supérieure à la médiane féminine).
    """
    # S'assurer de disposer des colonnes nécessaires
    if "Sexe" not in df.columns:
        raise ValueError("La colonne Sexe est requise pour réaliser l'analyse des écarts de rémunération par sexe.")

    # Le ratio M_div_F calculé plus bas ne reconnaît que les codes exacts "M" et "F" (cohérent avec
    # le reste du script, qui n'effectue aucune normalisation automatique des colonnes). Si la
    # colonne Sexe utilise d'autres codes (ex: "Homme"/"Femme", minuscules, espaces...), les
    # médianes par valeur sont quand même calculées mais la colonne M_div_F n'est jamais créée, sans
    # aucun message : on avertit explicitement ici plutôt que de laisser le ratio disparaître en silence.
    unexpected_codes = sorted(set(df["Sexe"].dropna().astype(str).unique()) - {"M", "F"})
    if unexpected_codes:
        print(
            f"[WARN] Colonne 'Sexe' : valeur(s) inattendue(s) {unexpected_codes} (seuls les codes "
            "'M' et 'F' sont reconnus) - le ratio M_div_F ne sera pas calculé pour ces lignes.",
            file=sys.stderr,
        )

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



