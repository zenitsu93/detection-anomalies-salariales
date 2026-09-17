#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Detection d'anomalies de remuneration par regression multivariee (OLS).

Pourquoi un signal supplementaire, en plus des regles deterministes et de l'IsolationForest
(anomaly_core.py) : les regles et l'IsolationForest reperent des salaires hors norme dans
l'absolu (bandes, marche) ou par rapport a des pairs proches (meme cohorte). La regression
repere autre chose : un salaire qui s'ecarte de ce que PREDISENT les facteurs de poste et de
carriere du salarie (famille de metier, grade, anciennete, age, competences, positionnement
9box, hot job) - un "sur-paye" ou "sous-paye" par rapport a son propre profil, meme s'il reste
dans la bande ou proche de ses pairs de cohorte.

Pourquoi statsmodels et non scikit-learn : contrairement a l'IsolationForest (une "boite noire"
qui ne sert qu'a scorer), on a besoin ici de coefficients interpretables, de p-values et
d'intervalles de confiance - notamment pour objectiver un ecart de remuneration Homme/Femme
"toutes choses egales par ailleurs" dans un rapport RH. C'est l'usage pour lequel statsmodels
(OLS) est concu ; scikit-learn ne fournit pas nativement ces informations.

Ce fichier est volontairement isole d'anomaly_core.py et n'est utilise QUE par le script CLI
detect_salary_anomalies_regression.py : il regroupe une mecanique specifique et plus
consequente que les autres signaux (construction dynamique de la formule, regroupement des
modalites rares, garde-fou sur la taille d'echantillon, extraction des residus studentises et
du coefficient Sexe) et une dependance (statsmodels/patsy) propre a cette seule brique. Le
pipeline "custom_fixed" (regles + IsolationForest) n'est pas modifie et ne depend pas de ce
fichier.
"""

import sys

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm

# -----------------------------------------------------------------------------
# Construction de la table d'analyse
# -----------------------------------------------------------------------------

# Memes variables que ml_features dans anomaly_core.ml_anomaly, plus Sexe (a la demande du
# client, pour objectiver un ecart Homme/Femme "toutes choses egales par ailleurs").
NUMERIC_CANDIDATES = ["Anciennete", "Age", "Competence_N1"]
CATEGORICAL_CANDIDATES = ["Job_Family", "Grade", "Positionnement_9BOX", "Hot_job", "Sexe"]


def _colonnes_numeriques_disponibles(df: pd.DataFrame) -> list:
    """Ne garde une colonne numerique candidate que si elle existe et contient au moins une
    valeur exploitable, comme le fait deja ml_anomaly (anomaly_core.py) pour ne pas planter si
    Competence_N1 est absente du fichier employes."""
    return [c for c in NUMERIC_CANDIDATES if c in df.columns and pd.to_numeric(df[c], errors="coerce").notna().any()]


def _colonnes_categorielles_disponibles(df: pd.DataFrame) -> list:
    """Ne garde une colonne categorielle candidate que si elle existe et comporte au moins 2
    modalites non manquantes : une colonne constante n'apporte rien au modele et produirait une
    colonne de design degeneree (parfaitement colineaire avec la constante)."""
    cols = []
    for c in CATEGORICAL_CANDIDATES:
        if c not in df.columns:
            continue
        n_modalites = df[c].dropna().astype(str).nunique()
        if n_modalites >= 2:
            cols.append(c)
    return cols


def _regrouper_modalites_rares(serie: pd.Series, effectif_min: int, label_autre: str = "Autre") -> pd.Series:
    """Remplace par 'Autre' toute modalite dont l'effectif (sur l'echantillon d'analyse) est
    strictement inferieur a effectif_min, pour eviter des colonnes de design quasi vides (donc
    peu fiables, voire une matrice singuliere) causees par des metiers/grades tres rares."""
    effectifs = serie.value_counts()
    rares = effectifs[effectifs < effectif_min].index
    if len(rares) == 0:
        return serie
    return serie.where(~serie.isin(rares), label_autre)


def _preparer_table_regression(df: pd.DataFrame, rule_params: dict):
    """Construit la table utilisee pour ajuster le modele (une copie : df n'est jamais modifie
    ici). Retourne (table, cols_num, cols_cat) ou (None, None, None) si aucune colonne
    categorielle exploitable ne reste (cas degenere, improbable mais a couvrir sans planter).
    """
    fixe = pd.to_numeric(df.get("Fixe_Annuel_MAD"), errors="coerce")
    job_family = df.get("Job_Family")
    grade = df.get("Grade")
    if job_family is None or grade is None:
        print("[WARN][REGRESSION] Colonnes Job_Family/Grade manquantes - signal de regression ignore.", file=sys.stderr)
        return None, None, None

    # Le logarithme du salaire exige une valeur finie strictement positive.
    exploitable = np.isfinite(fixe) & (fixe > 0) & job_family.notna() & grade.notna()
    n_exclues = int((~exploitable).sum())
    if n_exclues > 0:
        print(
            f"[WARN][REGRESSION] {n_exclues} ligne(s) exclue(s) de l'ajustement du modele "
            "(salaire manquant, non fini ou non positif, ou Job_Family/Grade manquant).",
            file=sys.stderr,
        )

    table = df.loc[exploitable].copy()
    if table.empty:
        return None, None, None

    cols_num = _colonnes_numeriques_disponibles(table)
    cols_cat = _colonnes_categorielles_disponibles(table)
    if not cols_cat:
        print("[WARN][REGRESSION] Aucune variable categorielle exploitable - signal de regression ignore.", file=sys.stderr)
        return None, None, None

    effectif_min = int(rule_params.get("reg_min_category_size", 10))
    for c in cols_cat:
        # fillna AVANT astype(str) : sinon un NaN deviendrait la chaine litterale "nan" (str(NaN))
        # au lieu du marqueur explicite "NA" voulu.
        table[c] = table[c].fillna("NA").astype(str)
        table[c] = _regrouper_modalites_rares(table[c], effectif_min)

    # Une colonne qui ne garde plus qu'une seule modalite apres regroupement (toutes ses
    # valeurs etaient rares) n'apporte plus rien au modele et doit etre retiree, sinon elle
    # produirait une colonne de design degeneree.
    cols_cat = [c for c in cols_cat if table[c].nunique() >= 2]
    if not cols_cat:
        print("[WARN][REGRESSION] Toutes les variables categorielles sont devenues constantes apres regroupement des modalites rares - signal de regression ignore.", file=sys.stderr)
        return None, None, None

    for c in cols_num:
        coerced = pd.to_numeric(table[c], errors="coerce")
        table[c] = coerced.fillna(coerced.median())

    # Cible en log plutot qu'en niveau : interpretation directe en %, et gere mieux
    # l'heteroscedasticite (des salaires eleves ont mecaniquement une variance absolue plus
    # grande) - pratique standard en econometrie salariale.
    table["_LogSalaire"] = np.log(pd.to_numeric(table["Fixe_Annuel_MAD"], errors="coerce"))

    return table, cols_num, cols_cat


def _niveau_reference_sexe(table: pd.DataFrame):
    """Determine la modalite de reference pour Sexe : 'F' si elle est effectivement presente
    apres nettoyage/regroupement des modalites rares, sinon la premiere modalite restante par
    ordre alphabetique. Sur un tres petit echantillon (ou apres regroupement), 'F' peut avoir
    disparu (ex: aucune femme dans l'extrait, ou toutes regroupees dans 'Autre') : forcer quand
    meme Treatment(reference="F") ferait planter patsy (PatsyError: specified level not found),
    d'ou ce choix dynamique plutot qu'une reference codee en dur."""
    modalites = sorted(table["Sexe"].dropna().unique())
    if not modalites:
        return None
    return "F" if "F" in modalites else modalites[0]


def _construire_formule(cols_num: list, cols_cat: list, table: pd.DataFrame) -> str:
    """Formule patsy additive uniquement (pas d'interaction Job_Family:Grade) : avec des
    dizaines de Job_Family et Grade, une interaction complete reintroduirait exactement le
    risque de colonnes quasi-vides / matrice singuliere que le regroupement des modalites
    rares cherche a eviter. Sexe (si present) est code avec une reference EXPLICITE (voir
    _niveau_reference_sexe), toujours 'F' quand elle existe, pour que le signe du coefficient
    soit directement comparable au ratio M_div_F de gender_gap_analysis (anomaly_core.py) :
    M_div_F > 1 <=> les hommes sont mieux payes, et ici un coefficient positif aura le meme
    sens. Le rapport M/F n'est fourni que si F reste la référence et M une modalité
    distincte après préparation des données."""
    termes = []
    for c in cols_cat:
        if c == "Sexe":
            reference = _niveau_reference_sexe(table)
            termes.append(f'C(Sexe, Treatment(reference="{reference}"))')
        else:
            termes.append(f"C({c})")
    termes.extend(cols_num)
    return "_LogSalaire ~ " + " + ".join(termes)


# -----------------------------------------------------------------------------
# Ajustement du modele
# -----------------------------------------------------------------------------

def fit_salary_regression(df: pd.DataFrame, rule_params: dict):
    """Ajuste le modele OLS predisant log(Fixe_Annuel_MAD) a partir des facteurs de poste et de
    carriere disponibles. Retourne (model, table, cols_cat), ou (None, None, None) si le
    garde-fou de taille d'echantillon echoue (jamais d'exception : le signal de regression est
    alors simplement absent, comme apply_ml_strong_signal renonce silencieusement en dessous de
    20 valeurs dans anomaly_core.py)."""
    table, cols_num, cols_cat = _preparer_table_regression(df, rule_params)
    if table is None:
        return None, None, None

    formule = _construire_formule(cols_num, cols_cat, table)
    y, X = patsy.dmatrices(formule, data=table, return_type="dataframe")

    n_obs, n_params = X.shape[0], X.shape[1]
    min_obs = int(rule_params.get("reg_min_observations", 50))
    min_obs_par_param = int(rule_params.get("reg_min_observations_per_param", 5))
    seuil = max(min_obs, min_obs_par_param * n_params)
    if n_obs < seuil:
        print(
            f"[WARN][REGRESSION] Echantillon trop petit par rapport au nombre de parametres du "
            f"modele (n={n_obs}, parametres={n_params}, seuil requis={seuil}) - signal de "
            "regression ignore.",
            file=sys.stderr,
        )
        return None, None, None

    if np.linalg.matrix_rank(X.values) < n_params:
        print(
            "[WARN][REGRESSION] Matrice de conception singuliere (colonnes colineaires malgre le "
            "regroupement des modalites rares) - signal de regression ignore.",
            file=sys.stderr,
        )
        return None, None, None

    model = sm.OLS(y, X).fit()
    return model, table, cols_cat


# -----------------------------------------------------------------------------
# Residus et score d'anomalie
# -----------------------------------------------------------------------------

def calculer_signal_regression(df: pd.DataFrame, model, table: pd.DataFrame) -> pd.DataFrame:
    """Ajoute Salaire_Predit_Regression, Residu_Regression et Reg_AnomalyScore a df. Les lignes
    non incluses dans l'ajustement (cf _preparer_table_regression) restent a NaN sur ces 3
    colonnes."""
    # Residus studentises EXTERNES (et non internes) : c'est la statistique standard utilisee
    # pour du outlier testing, plus robuste qu'un residu interne car elle estime la variance en
    # laissant chaque observation de cote (leave-one-out), ce qui evite qu'un point vraiment
    # aberrant ne "tire" sa propre variance de reference vers le haut et ne minimise ainsi son
    # propre residu standardise.
    #
    # Calcule ici via la formule analytique fermee (Belsley/Kuh/Welsch), et NON via
    # model.get_influence().resid_studentized_external : cette derniere refait un vrai fit OLS
    # pour chaque observation laissee de cote (boucle de taille n, chaque fit en O(n*p^2)), donc
    # O(n^2*p^2) au total - sur un fichier de plusieurs milliers de salaries, cela rend le script
    # impraticable (verifie : plusieurs minutes sur 10 000 lignes). La formule fermee ci-dessous
    # est mathematiquement identique (verifie a 1e-14 pres sur un cas de test) et ne coute que
    # O(n*p), grace au fait que hat_matrix_diag (le levier de chaque observation) se deduit du
    # modele deja ajuste, sans le reajuster.
    infl = model.get_influence()
    h = infl.hat_matrix_diag
    e = model.resid.to_numpy()
    n_obs = model.nobs
    p = model.df_model + 1  # +1 : df_model n'inclut pas l'intercept
    s2 = model.mse_resid
    s2_looo = ((n_obs - p) * s2 - e ** 2 / (1 - h)) / (n_obs - p - 1)
    resid_studentises = e / np.sqrt(s2_looo * (1 - h))
    resid = pd.Series(resid_studentises, index=table.index).reindex(df.index)
    predit = pd.Series(np.exp(model.fittedvalues), index=table.index).reindex(df.index)

    df["Salaire_Predit_Regression"] = predit
    df["Residu_Regression"] = resid

    base = resid.abs()
    valides = base.dropna()
    if len(valides) and valides.max() > valides.min():
        norm = 100 * (base - valides.min()) / (valides.max() - valides.min())
        norm = norm.clip(0, 100)
    else:
        # Meme convention que ml_anomaly (anomaly_core.py) quand min==max : un score neutre de
        # 50 pour les lignes valides, NaN conserve pour les lignes exclues de l'ajustement.
        norm = base.where(base.isna(), 50.0)
    df["Reg_AnomalyScore"] = norm
    return df


def regression_anomaly(df: pd.DataFrame, rule_params: dict):
    """Point d'entree unique de ce module. Retourne (df, model_or_None) : contrairement aux
    autres fonctions du pipeline (qui ne renvoient que df), on renvoie aussi le modele ajuste
    car regression_gender_gap_report() en a besoin pour extraire le coefficient Sexe."""
    model, table, cols_cat = fit_salary_regression(df, rule_params)
    if model is None:
        df["Salaire_Predit_Regression"] = np.nan
        df["Residu_Regression"] = np.nan
        df["Reg_AnomalyScore"] = np.nan
        return df, None
    df = calculer_signal_regression(df, model, table)
    return df, model


# -----------------------------------------------------------------------------
# Agregation du risque (replique locale de anomaly_core.aggregate_risk, avec un 3e signal)
# -----------------------------------------------------------------------------

def aggregate_risk_with_regression(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Variante de anomaly_core.aggregate_risk qui combine 3 signaux (regles, IsolationForest,
    regression) au lieu de 2. Duplique intentionnellement la logique de buckets de severite
    (identique a anomaly_core.aggregate_risk) plutot que de modifier ce fichier partage, pour
    que le pipeline existant (detect_salary_anomalies_custom_fixed.py) reste inchange."""
    rule_w = float(rule_params.get("rule_weight", 0.6))
    ml_w = float(rule_params.get("ml_weight", 0.25))
    reg_w = float(rule_params.get("reg_weight", 0.15))

    reg_score = df["Reg_AnomalyScore"] if "Reg_AnomalyScore" in df.columns else pd.Series(0.0, index=df.index)
    df["RiskScore"] = (
        rule_w * df["Rule_Score"].fillna(0)
        + ml_w * df["ML_AnomalyScore"].fillna(0)
        + reg_w * reg_score.fillna(0)
    )

    buckets = rule_params.get("prioritization_buckets", {
        "Critical": [70, 100],
        "Major": [50, 69],
        "Minor": [30, 49],
        "Info": [0, 29],
    })
    categories_par_severite_decroissante = sorted(buckets.items(), key=lambda item: item[1][0], reverse=True)

    def sev(x):
        for name, (lo, _hi) in categories_par_severite_decroissante:
            if x >= lo:
                return name
        return "Info"

    df["Severity"] = df["RiskScore"].apply(sev)
    return df


# -----------------------------------------------------------------------------
# Rapport d'ecart Homme/Femme "ajuste"
# -----------------------------------------------------------------------------



# -----------------------------------------------------------------------------
# Validation des parametres propres a ce module
# -----------------------------------------------------------------------------

EXPECTED_REGRESSION_KEYS = {
    "rule_weight": 0.6,
    "ml_weight": 0.25,
    "reg_weight": 0.15,
    "reg_min_category_size": 10,
    "reg_min_observations": 50,
    "reg_min_observations_per_param": 5,
}


def validate_regression_params(rule_params: dict) -> None:
    """Equivalent local de anomaly_core.validate_rule_params, mais uniquement pour les clefs
    propres a ce module. anomaly_core.validate_rule_params ne connait pas ces clefs (reg_weight,
    reg_min_*) et produirait un faux avertissement "cle absente" a chaque run si on l'appelait
    telle quelle sur un rulebook qui les definit ; ce module a donc sa propre validation, plutot
    que d'etendre EXPECTED_RULE_KEYS dans anomaly_core.py."""
    for key, default in EXPECTED_REGRESSION_KEYS.items():
        if key not in rule_params:
            print(f"[WARN][RULEBOOK][REGRESSION] Cle 'rules.{key}' absente - valeur par defaut utilisee: {default}", file=sys.stderr)
