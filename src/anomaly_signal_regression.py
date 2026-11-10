#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Régression du salaire : le « salaire attendu » de chaque salarié, vu son poste et son profil.

Ce que fait ce fichier, et pourquoi (refonte du 10/11/2026) :
- Validation croisée en 5 paquets : le modèle apprend sur 4 paquets et prédit le 5e, qu'il n'a pas vu ;
  on recommence pour chaque paquet. Chaque salarié reçoit ainsi un salaire attendu calculé SANS LUI
  (Salaire_Attendu). Pourquoi : un salaire anormal qui sert à apprendre tire le modèle vers lui et se
  cache ; prédit par un modèle qui ne l'a pas vu, il ressort. Les qualités (R2, MAE...) sont mesurées sur
  les 10 000 salariés au lieu de 2 000, donc plus fiables qu'avec un seul tirage 80 % / 20 %.
- Apprentissage robuste : un premier modèle repère les salaires très loin de ce qu'il attend (plus de
  trois écarts habituels, voir ecart_robuste) ; ils n'apprennent pas au modèle final. Pourquoi : les
  anomalies qu'on cherche ne doivent pas servir d'exemple de « salaire normal ».
- Fourchette : tirée des erreurs des salariés non vus (méthode dite « conforme ») ; on vérifie ensuite
  qu'elle contient bien 9 salaires sur 10 (Couverture), niveau par niveau dans le diagnostic.
- L'écart au salaire attendu (Ecart_Attendu, en %) et sa mesure en écarts habituels (Z_Attendu)
  servent à l'IA de la détection (voir score_ecart_attendu) : un salarié payé nettement moins que ce
  que son poste ET son profil laissent attendre est un cas à regarder, même s'il est dans sa grille.
- Effets en % (effets) : « à profil égal, un an d'ancienneté en plus = tant de % de salaire en plus ».

Ce qu'il ne lit pas, et pourquoi :
- le salaire lui-même : c'est ce qu'il doit deviner. Le lui donner, ce serait lui donner la réponse ;
- le Min et le Max de la grille : ils se déduisent du Mid, ils ne diraient rien de plus ;
- la médiane du marché seule : avec le Mid et le ratio grille / marché, elle est déjà connue ;
- le sexe : le modèle apprendrait l'écart de salaire entre femmes et hommes et le recopierait. Il sert
  seulement APRÈS, dans le diagnostic, pour mesurer l'écart femmes / hommes à profil égal ;
- le pôle : deux salariés du même métier et du même niveau ne doivent pas être payés différemment parce
  qu'ils sont dans deux pôles différents.

Utilisation, depuis le dossier du projet :
      python src/anomaly_signal_regression.py
Il écrit output/regression/diagnostic_regression.xlsx : qualité du modèle, effets en %, utilité de
chaque variable, écart femmes / hommes à profil égal.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, RepeatedKFold

from anomaly_pretraitement import preparer_employes

# Le tableau unique des colonnes que lit le modèle, avec leur type. Pour en retirer une, effacer sa
# ligne ; pour en ajouter une, ajouter une ligne.
# - « catégorie » : chaque valeur a son propre effet (colonnes 0/1). Le 9-Box l'est même s'il est écrit
#   avec des chiffres : ses cases ne sont pas rangées de la moins bonne à la meilleure.
# - « nombre » : un seul effet, « tant de % de salaire en plus par unité en plus ».
COLONNES = {
    "Job_Family": "catégorie",           # le métier
    "Niveau": "catégorie",               # le niveau (1 à 7)
    "Mid": "nombre",                     # le milieu de la grille du métier + niveau
    "Ratio_Grille_Marche": "nombre",     # Mid / médiane du marché : 1,10 = la grille paie 10 % de plus
    "Anciennete": "nombre",              # en années
    "Age": "nombre",                     # en années
    "Competence_N1": "nombre",           # la note de compétence de l'an dernier
    "Performance_N1": "catégorie",       # la performance de l'an dernier (« A l'objectif »...)
    "Positionnement_9BOX": "catégorie",  # la case 9-Box
    "Hot_job": "nombre",                 # la tension du métier sur le marché (0 à 2)
    "Rang_Etude_Max": "nombre",          # le niveau d'études : 0 = secondaire, 1 = BAC... 7 = BAC+7
    "Cat_Ecole_Max": "catégorie",        # la catégorie d'école (ingénieur, commerce, université, autres)
}
# Pourquoi le niveau d'études en nombre (son rang) : certains niveaux comptent très peu de salariés
# (BAC+6, expertise comptable), le modèle ne pourrait rien apprendre sur eux seuls ; avec le rang, il
# apprend un seul effet, qui vaut pour tous les niveaux.


def tableau_x(df: pd.DataFrame, colonnes) -> pd.DataFrame:
    """Le tableau que lit le modèle : les colonnes demandées, les catégories en colonnes 0/1.
    - Le Mid est lu en logarithme, comme le salaire : « 10 % de Mid en plus » donne alors le même effet
      en % à tous les niveaux.
    - Une catégorie vide devient « Inconnu », qui a sa propre colonne 0/1. Une colonne de texte absente
      de COLONNES (la compétence, si elle est écrite en libellés) est elle aussi lue en catégorie.
    - Un niveau d'études inconnu : rang mis à 0, et une colonne « Rang_Etude_Inconnu » à 1, qui reçoit
      son propre effet (sinon il compterait comme « secondaire »).
    - Une autre case vide parmi les nombres reste vide : ce salarié n'apprend pas au modèle et n'a pas
      de salaire prédit."""
    x = df[list(colonnes)].copy()
    if "Mid" in x:
        x["Mid"] = np.log(x["Mid"].where(x["Mid"] > 0))
    if "Rang_Etude_Max" in x:
        rang = pd.to_numeric(x["Rang_Etude_Max"], errors="coerce")
        x["Rang_Etude_Inconnu"] = rang.isna().astype(float)
        x["Rang_Etude_Max"] = rang.fillna(0)
    categories = [c for c in colonnes if COLONNES.get(c) == "catégorie" or not pd.api.types.is_numeric_dtype(x[c])]
    for colonne in categories:
        x[colonne] = x[colonne].astype(object).where(x[colonne].notna(), "Inconnu").astype(str)
    return pd.get_dummies(x, columns=categories, dtype=float)


# Les colonnes qui décrivent le POSTE (sa grille), et pas la personne. L'explication de l'IA ne les cite
# pas : « payé moins que prévu parce qu'il est au niveau 5 » n'apprend rien ; ce qui compte, c'est ce
# qui, dans le PROFIL, relève le salaire attendu (ancienneté, performance...).
POSTE = ("Job_Family", "Niveau", "Mid", "Ratio_Grille_Marche")
# Noms des colonnes en clair, pour l'explication et le diagnostic.
NOMS = {
    "Job_Family": "le métier", "Niveau": "le niveau", "Mid": "le milieu de grille",
    "Ratio_Grille_Marche": "le ratio grille / marché", "Anciennete": "l'ancienneté", "Age": "l'âge",
    "Competence_N1": "la compétence N-1", "Performance_N1": "la performance N-1",
    "Positionnement_9BOX": "le 9-Box", "Hot_job": "le Hot job", "Rang_Etude_Max": "le niveau d'études",
    "Cat_Ecole_Max": "la catégorie d'école",
}
# Seuil de l'apprentissage robuste : un salaire à plus de 3 écarts habituels de ce qu'attend le premier
# modèle n'apprend pas au modèle final (sous une loi normale, 3 salariés sur 1 000 seulement le dépassent).
SEUIL_ROBUSTE = 3.0
# Nombre de paquets de la validation croisée.
PAQUETS = 5


def ecart_robuste(residus):
    """Le centre (médiane) et l'écart habituel d'une série d'erreurs, insensibles aux valeurs extrêmes.
    Pourquoi pas la moyenne et l'écart-type : quelques salaires très anormaux les gonfleraient, et les
    autres paraîtraient alors tous normaux. 1,4826 × l'écart médian vaut l'écart-type quand il n'y a pas
    d'anomalie (même recette que robust_zscore dans anomaly_cohortes.py)."""
    residus = np.asarray(residus, dtype=float)
    centre = float(np.median(residus))
    echelle = 1.4826 * float(np.median(np.abs(residus - centre)))
    if not echelle > 0:
        echelle = float(np.std(residus)) or 1.0
    return centre, echelle


def _robuste(X, Y):
    """Apprend en deux temps : un premier modèle, puis le modèle final sans les salaires très loin de ce
    qu'attendait le premier (SEUIL_ROBUSTE). Rend le modèle final et le masque des salariés gardés."""
    premier = LinearRegression().fit(X, Y)
    residus = Y - premier.predict(X)
    centre, echelle = ecart_robuste(residus)
    garde = np.abs(residus - centre) <= SEUIL_ROBUSTE * echelle
    return LinearRegression().fit(X[garde], Y[garde]), garde


def _donnees(df, colonnes):
    """Le tableau X que lit le modèle et le log du salaire Y, pour les salariés complets (salaire > 0 et
    aucune case vide parmi les nombres)."""
    df = df[pd.to_numeric(df["Fixe_Annuel_MAD"], errors="coerce") > 0]
    X = tableau_x(df, colonnes)
    X = X[X.notna().all(axis=1)]
    # Log du salaire : l'écart se lit en %, comparable d'un niveau à l'autre
    Y = np.log(df.loc[X.index, "Fixe_Annuel_MAD"].astype(float))
    return X, Y


def hors_echantillon(X, Y, random_state=42):
    """Le log du salaire attendu de chaque salarié, prédit par un modèle qui ne l'a pas vu (validation
    croisée en PAQUETS paquets), et le masque des salariés que l'apprentissage robuste a gardés dans au
    moins un modèle. random_state=42 : le même découpage à chaque lancement."""
    predit = pd.Series(np.nan, index=X.index)
    garde_total = pd.Series(False, index=X.index)
    for apprend, verifie in KFold(PAQUETS, shuffle=True, random_state=random_state).split(X):
        modele, garde = _robuste(X.iloc[apprend], Y.iloc[apprend])
        predit.iloc[verifie] = modele.predict(X.iloc[verifie])
        garde_total.iloc[apprend] |= garde.to_numpy()
    return predit, garde_total


def entrainer(df: pd.DataFrame, colonnes=None):
    """Entraîne le modèle. colonnes : ce que lit le modèle ; sans précision, celles de COLONNES que le
    tableau a, avec au moins une case remplie (une colonne absente du fichier est laissée de côté).
    analyse_diplomes/diplome.py en donne d'autres, pour comparer le modèle sans et avec le diplôme.

    Rend le modèle (un dictionnaire, voir predire) et ses qualités, mesurées sur des salariés que le
    modèle n'a pas vus (validation croisée) :
    - R2 : part des différences de salaire (en %) que le modèle explique (1 = toutes) ;
    - MAE et RMSE : erreur moyenne en kMAD ; MAPE : erreur moyenne en % du salaire ;
    - Couverture : part des salaires qui tombent dans la fourchette (visée : 90 %)."""
    if colonnes is None:
        colonnes = [c for c in COLONNES if c in df and df[c].notna().any()]
    X, Y = _donnees(df, colonnes)

    predit, _ = hors_echantillon(X, Y)
    residus = Y - predit
    # Fourchette : on range les erreurs des salariés non vus, et on retire les 5 % les plus basses et les
    # 5 % les plus hautes. Pourquoi seulement les salariés « normaux » (à moins de SEUIL_ROBUSTE écarts) :
    # la fourchette dit où tombe un salaire normal pour ce profil ; les anomalies l'élargiraient.
    centre, echelle = ecart_robuste(residus)
    normaux = np.abs(residus - centre) <= SEUIL_ROBUSTE * echelle
    bas, haut = np.quantile(residus[normaux], [0.05, 0.95])

    # Qualités, sur les salariés normaux : on mesure si le modèle devine bien un salaire normal. Les
    # anomalies, par définition loin de ce qui est attendu, feraient croire à un mauvais modèle.
    y, p = Y[normaux], predit[normaux]
    vrai, devine = np.exp(y), np.exp(p)
    metriques = {
        "R2": float(1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)),
        "MAE": float(np.mean(np.abs(vrai - devine))),
        "RMSE": float(np.mean((vrai - devine) ** 2) ** 0.5),
        "MAPE": float(np.mean(np.abs(vrai / devine - 1))),
        "Couverture": float(np.mean((residus >= bas) & (residus <= haut))),
        "Exclus_Apprentissage": float(1 - normaux.mean()),
    }

    # Le modèle final apprend sur tous les salariés (toujours en robuste) : c'est lui que l'aide à la
    # décision interroge pour un nouveau profil.
    modele, garde = _robuste(X, Y)
    reg = {
        "modele": modele,
        # Pourquoi garder la liste des colonnes lues : predire doit refaire exactement le même tableau.
        "colonnes": list(colonnes),
        "colonnes_X": list(X.columns),
        "fourchette": (float(bas), float(haut)),
        "centre": centre,
        "echelle": echelle,
        # Le profil moyen des salariés qui ont appris : l'explication compare chacun à lui.
        "moyenne_X": X[garde].mean(),
    }
    return reg, metriques


def predire(profils: pd.DataFrame, reg: dict) -> pd.DataFrame:
    """profils : les colonnes du modèle. Un profil avec une case vide parmi les nombres n'a pas de
    salaire prédit (cases vides)."""
    profils = profils.copy()
    # Mêmes colonnes 0/1 qu'à l'entraînement. Une valeur jamais vue à l'entraînement (un nouveau
    # métier...) n'a pas de colonne : elle compte comme la valeur de référence.
    X = tableau_x(profils, reg["colonnes"]).reindex(columns=reg["colonnes_X"], fill_value=0)
    complet = X.notna().all(axis=1).to_numpy()
    log_predit = np.full(len(X), np.nan)
    if complet.any():
        log_predit[complet] = reg["modele"].predict(X[complet])
    bas, haut = reg["fourchette"]

    profils["Salaire_Predit"] = np.exp(log_predit)
    profils["Fourchette_Basse"] = np.exp(log_predit + bas)
    profils["Fourchette_Haute"] = np.exp(log_predit + haut)
    return profils


def colonne_source(colonne_x, colonnes):
    """La colonne d'origine d'une colonne de X : « Performance_N1_A l'objectif » -> « Performance_N1 »,
    « Rang_Etude_Inconnu » -> « Rang_Etude_Max »."""
    if colonne_x == "Rang_Etude_Inconnu":
        return "Rang_Etude_Max"
    for c in sorted(colonnes, key=len, reverse=True):
        if colonne_x == c or colonne_x.startswith(c + "_"):
            return c
    return colonne_x


def contributions(X: pd.DataFrame, reg: dict) -> pd.DataFrame:
    """Pour chaque salarié et chaque colonne d'origine, de combien elle relève (ou baisse) son salaire
    attendu par rapport au profil moyen, en log. Pourquoi c'est exact : le modèle est une somme
    d'effets ; l'écart au profil moyen est donc la somme des écarts de chaque colonne. Les colonnes 0/1
    d'une même catégorie (la performance...) sont additionnées."""
    effets = (X[reg["colonnes_X"]] - reg["moyenne_X"]) * reg["modele"].coef_
    sources = [colonne_source(c, reg["colonnes"]) for c in reg["colonnes_X"]]
    return effets.T.groupby(sources).sum().T


def score_ecart_attendu(df: pd.DataFrame, rule_params: dict, colonnes=None) -> pd.DataFrame:
    """Le signal de l'IA fondé sur l'écart au salaire attendu. Rend un NOUVEAU DataFrame avec :
    - Salaire_Attendu, Attendu_Bas, Attendu_Haut : le salaire attendu et sa fourchette (9 fois sur 10),
      prédits par un modèle qui n'a pas vu le salarié ;
    - Ecart_Attendu : salaire / salaire attendu - 1 (-0,15 = payé 15 % de moins qu'attendu) ;
    - Z_Attendu : cet écart en écarts habituels (-2 = nettement sous l'attendu, -3 = très en dessous) ;
    - ML_AnomalyScore : 0 si le salaire est au niveau attendu ou au-dessus, puis monte jusqu'à 100 quand
      Z_Attendu atteint -ml_z_plein (3 par défaut). Pourquoi d'un seul côté : depuis le comité du
      15/10/2026, être payé au-dessus n'est pas un cas à traiter. Pourquoi un seuil fixe plutôt que « de 0
      pour le plus banal à 100 pour le plus atypique du fichier » : le même score veut alors dire la même
      chose d'un fichier à l'autre, et un seul salarié extrême n'écrase plus le score de tous les autres.
    Un salarié sans salaire attendu (pas de grille, âge manquant...) a un score de 0."""
    z_plein = float(rule_params.get("ml_z_plein", 3.0))
    df = df.copy()
    if colonnes is None:
        colonnes = [c for c in COLONNES if c in df and df[c].notna().any()]
    X, Y = _donnees(df, colonnes)
    predit, _ = hors_echantillon(X, Y)
    residus = Y - predit
    centre, echelle = ecart_robuste(residus)
    normaux = np.abs(residus - centre) <= SEUIL_ROBUSTE * echelle
    bas, haut = np.quantile(residus[normaux], [0.05, 0.95])

    for colonne in ["Salaire_Attendu", "Attendu_Bas", "Attendu_Haut", "Ecart_Attendu", "Z_Attendu"]:
        df[colonne] = np.nan
    df.loc[X.index, "Salaire_Attendu"] = np.exp(predit)
    df.loc[X.index, "Attendu_Bas"] = np.exp(predit + bas)
    df.loc[X.index, "Attendu_Haut"] = np.exp(predit + haut)
    df.loc[X.index, "Ecart_Attendu"] = np.exp(residus) - 1
    df.loc[X.index, "Z_Attendu"] = (residus - centre) / echelle
    df["ML_AnomalyScore"] = (100 * (-df["Z_Attendu"] / z_plein).clip(0, 1)).fillna(0.0)
    return df


# -----------------------------------------------------------------------------
# Diagnostic : la qualité du modèle et l'utilité de chaque variable, sur les vraies données
# -----------------------------------------------------------------------------

def effets(df: pd.DataFrame, colonnes=None) -> pd.DataFrame:
    """L'effet de chaque colonne sur le salaire attendu, en %, à tout le reste égal, avec son
    intervalle de confiance à 95 %. Pour une catégorie, l'effet se lit par rapport à la valeur la plus
    fréquente (la « référence »). Pourquoi un intervalle : un effet de +2 % dont l'intervalle va de -1 %
    à +5 % peut venir du hasard ; on ne bâtit pas une politique salariale dessus."""
    if colonnes is None:
        colonnes = [c for c in COLONNES if c in df and df[c].notna().any()]
    X, Y = _donnees(df, colonnes)
    modele, garde = _robuste(X, Y)
    X, Y = X[garde], Y[garde]
    # Pourquoi refaire le tableau : pour lire chaque catégorie par rapport à sa valeur la plus fréquente,
    # on retire sa colonne 0/1 (sinon les effets d'une catégorie ne sont pas séparables de la constante).
    a_retirer = []
    for c in colonnes:
        groupe = [x for x in X.columns if colonne_source(x, colonnes) == c and x != c and x != "Rang_Etude_Inconnu"]
        if groupe:
            a_retirer.append(X[groupe].sum().idxmax())
    Xr = X.drop(columns=a_retirer)
    Xr = Xr.loc[:, Xr.std() > 0]
    A = np.column_stack([np.ones(len(Xr)), Xr.to_numpy()])
    coef, *_ = np.linalg.lstsq(A, Y.to_numpy(), rcond=None)
    residus = Y.to_numpy() - A @ coef
    variance = residus @ residus / (len(A) - A.shape[1])
    erreur = np.sqrt(np.diag(variance * np.linalg.pinv(A.T @ A)))[1:]
    coef = coef[1:]
    lignes = []
    for nom_x, b, e in zip(Xr.columns, coef, erreur):
        source = colonne_source(nom_x, colonnes)
        reference = next((r for r in a_retirer if colonne_source(r, colonnes) == source), None)
        valeur = nom_x[len(source) + 1:] if nom_x.startswith(source + "_") else ("+1" if nom_x == source else nom_x)
        if source == "Mid":
            valeur = "+10 % de Mid"
            b, e = b * np.log(1.1), e * np.log(1.1)
        lignes.append({
            "Variable": NOMS.get(source, source), "Valeur": valeur,
            "Reference": reference[len(source) + 1:] if reference else "",
            "Effet_%": np.exp(b) - 1, "Effet_Bas_%": np.exp(b - 1.96 * e) - 1,
            "Effet_Haut_%": np.exp(b + 1.96 * e) - 1,
            "Sur": "oui" if abs(b) > 1.96 * e else "non",
        })
    return pd.DataFrame(lignes)


def utilite_variables(df: pd.DataFrame, colonnes=None, repetitions=3) -> pd.DataFrame:
    """De combien l'erreur moyenne (en %) augmente quand on RETIRE chaque variable, mesuré sur des
    salariés non vus (validation croisée répétée). Une variable dont le retrait ne change rien (ou fait
    mieux) n'aide pas la prédiction : elle peut être retirée de COLONNES. Pourquoi « retirer » plutôt que
    regarder le coefficient : deux variables qui disent la même chose (le 9-Box et la performance) ont
    chacune un petit coefficient, mais retirer l'une ne coûte rien puisque l'autre reste."""
    if colonnes is None:
        colonnes = [c for c in COLONNES if c in df and df[c].notna().any()]
    base = df[pd.to_numeric(df["Fixe_Annuel_MAD"], errors="coerce") > 0]
    complet = tableau_x(base, colonnes).notna().all(axis=1)
    base = base[complet]
    Y = np.log(base["Fixe_Annuel_MAD"].astype(float))
    decoupage = list(RepeatedKFold(n_splits=PAQUETS, n_repeats=repetitions, random_state=42).split(base))

    def erreur(cols):
        X = tableau_x(base, cols)
        erreurs = []
        for apprend, verifie in decoupage:
            modele, _ = _robuste(X.iloc[apprend], Y.iloc[apprend])
            r = Y.iloc[verifie] - modele.predict(X.iloc[verifie])
            centre, echelle = ecart_robuste(r)
            r = r[np.abs(r - centre) <= SEUIL_ROBUSTE * echelle]
            erreurs.append(np.mean(np.abs(np.exp(r) - 1)))
        return float(np.mean(erreurs))

    reference = erreur(colonnes)
    lignes = [{"Variable": "(toutes)", "Erreur_Moyenne_%": reference, "Gain_Apporte_points_%": 0.0}]
    for c in colonnes:
        e = erreur([x for x in colonnes if x != c])
        lignes.append({"Variable": NOMS.get(c, c), "Erreur_Moyenne_%": e,
                       "Gain_Apporte_points_%": e - reference,
                       "Verdict": "utile" if e - reference > 0.0005 else "n'aide pas"})
    return pd.DataFrame(lignes)


def comparer_boosting(df: pd.DataFrame, colonnes=None) -> dict:
    """Erreur moyenne (en %) d'un modèle non linéaire (gradient boosting) contre la régression, sur des
    salariés non vus. Pourquoi : si le boosting fait nettement mieux, le salaire dépend des variables
    d'une façon que la régression ne sait pas suivre (l'ancienneté qui compte moins après 20 ans...) ;
    sinon, la régression, lisible effet par effet, est le bon choix."""
    if colonnes is None:
        colonnes = [c for c in COLONNES if c in df and df[c].notna().any()]
    X, Y = _donnees(df, colonnes)
    resultat = {}
    for nom_modele in ["Régression", "Gradient boosting"]:
        erreurs = []
        for apprend, verifie in KFold(PAQUETS, shuffle=True, random_state=42).split(X):
            if nom_modele == "Régression":
                modele, _ = _robuste(X.iloc[apprend], Y.iloc[apprend])
            else:
                modele = HistGradientBoostingRegressor(loss="absolute_error", random_state=42)
                modele.fit(X.iloc[apprend], Y.iloc[apprend])
            r = Y.iloc[verifie] - modele.predict(X.iloc[verifie])
            centre, echelle = ecart_robuste(r)
            r = r[np.abs(r - centre) <= SEUIL_ROBUSTE * echelle]
            erreurs.append(np.mean(np.abs(np.exp(r) - 1)))
        resultat[nom_modele] = float(np.mean(erreurs))
    return resultat


def couverture_par_niveau(df: pd.DataFrame, colonnes=None) -> pd.DataFrame:
    """Pour chaque niveau : part des salaires dans la fourchette (visée 90 %) et erreur moyenne en %.
    Pourquoi : une fourchette juste « en moyenne » peut être trop étroite pour les hauts niveaux, où les
    salaires varient davantage, et trop large pour les autres."""
    d = score_ecart_attendu(df, {}, colonnes)
    d = d[d["Salaire_Attendu"].notna()]
    dans = (d["Fixe_Annuel_MAD"] >= d["Attendu_Bas"]) & (d["Fixe_Annuel_MAD"] <= d["Attendu_Haut"])
    return (d.assign(Dans=dans, Erreur=d["Ecart_Attendu"].abs())
            .groupby("Niveau").agg(Salaries=("Dans", "size"), Couverture=("Dans", "mean"),
                                   Erreur_Mediane_pct=("Erreur", "median")).reset_index())


def ecart_femmes_hommes(df: pd.DataFrame, colonnes=None) -> pd.DataFrame:
    """L'écart de salaire femmes / hommes À PROFIL ÉGAL, par métier et en tout : la moyenne de l'écart
    au salaire attendu des femmes moins celle des hommes. Le modèle ne lit pas le sexe : il attend le
    même salaire pour une femme et un homme de même profil ; ce qui reste est l'écart que le poste, le
    profil et la performance n'expliquent pas. -3 % : à profil égal, les femmes sont payées 3 % de moins.
    Pourquoi en plus de l'écart des médianes (anomaly_ecarts_hommes_femmes.py) : un écart brut peut venir
    de profils différents (plus d'ancienneté d'un côté) ; celui-ci les met à égalité."""
    if "Sexe" not in df:
        return pd.DataFrame()
    d = score_ecart_attendu(df, {}, colonnes)
    d = d[d["Ecart_Attendu"].notna() & d["Sexe"].isin(["F", "M"])]
    d = d.assign(Log=np.log1p(d["Ecart_Attendu"]))

    def ligne(groupe, nom_groupe):
        f, h = groupe.loc[groupe.Sexe == "F", "Log"], groupe.loc[groupe.Sexe == "M", "Log"]
        if len(f) < 10 or len(h) < 10:
            return None
        ecart = f.mean() - h.mean()
        erreur = np.sqrt(f.var() / len(f) + h.var() / len(h))
        return {"Perimetre": nom_groupe, "Femmes": len(f), "Hommes": len(h),
                "Ecart_Profil_Egal_%": np.exp(ecart) - 1,
                "Bas_%": np.exp(ecart - 1.96 * erreur) - 1, "Haut_%": np.exp(ecart + 1.96 * erreur) - 1,
                "Sur": "oui" if abs(ecart) > 1.96 * erreur else "non"}

    lignes = [ligne(d, "Toute l'entreprise")]
    lignes += [ligne(g, metier) for metier, g in d.groupby("Job_Family")]
    return pd.DataFrame([x for x in lignes if x])


if __name__ == "__main__":
    projet = Path(__file__).resolve().parent.parent
    df = preparer_employes(projet / "input" / "employes.xlsx",
                           projet / "input" / "bands.xlsx",
                           projet / "input" / "market.xlsx")

    # 1. Entraîner le modèle et l'enregistrer
    dossier = projet / "models"
    dossier.mkdir(exist_ok=True)
    reg, metriques = entrainer(df)
    joblib.dump(reg, dossier / "regression.joblib")
    print("Colonnes lues :", ", ".join(reg["colonnes"]))
    print(f"Qualité sur des salariés non vus : R2 = {metriques['R2']:.3f}, erreur moyenne = "
          f"{metriques['MAE']:.1f} kMAD ({metriques['MAPE']:.1%}), fourchette juste "
          f"{metriques['Couverture']:.0%} du temps (visé : 90 %)")

    # 2. Le diagnostic, dans un fichier Excel
    print("Diagnostic en cours (utilité de chaque variable, quelques secondes)...")
    boosting = comparer_boosting(df)
    qualite = pd.DataFrame([{"Mesure": k, "Valeur": v} for k, v in metriques.items()]
                           + [{"Mesure": f"Erreur moyenne % - {k}", "Valeur": v} for k, v in boosting.items()])
    sortie = projet / "output" / "regression" / "diagnostic_regression.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(sortie) as excel:
        qualite.to_excel(excel, sheet_name="Qualite", index=False)
        couverture_par_niveau(df).to_excel(excel, sheet_name="Fourchette_par_niveau", index=False)
        effets(df).to_excel(excel, sheet_name="Effets", index=False)
        utilite_variables(df).to_excel(excel, sheet_name="Utilite_variables", index=False)
        ecart_femmes_hommes(df).to_excel(excel, sheet_name="Femmes_Hommes_profil_egal", index=False)
    print(f"Diagnostic enregistré dans : {sortie}")
