#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SIGNAL ML : REPÉRER LES PROFILS ATYPIQUES AVEC L'INTELLIGENCE ARTIFICIELLE
==========================================================================

Ce fichier calcule, pour chaque salarié, un score d'anomalie de 0 à 100 (ML_AnomalyScore) avec un
modèle d'intelligence artificielle, l'Isolation Forest.

Il prend en entrée le DataFrame rendu par anomaly_regles.py et rend ce DataFrame complété de la
colonne ML_AnomalyScore.

Utilisation :
- depuis Python :
      from anomaly_signal_iforest import ml_anomaly
      df = ml_anomaly(df, rule_params)
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_signal_iforest.py
  Le DataFrame est enregistré dans output/signal_iforest/employes_signal_iforest.xlsx, à ouvrir
  avec Excel.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import IsolationForest

from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_regression import score_ecart_attendu

# Les colonnes que le modèle regarde : le salaire et ses ratios, l'âge, l'ancienneté et les champs RH
# (compétence et performance N-1, Hot job).
# Changements du 10/11/2026, et pourquoi :
# - RangePenetration retirée : elle se calcule avec le Min et le Max de la grille et dit presque la
#   même chose que le CompaRatio (où est le salaire dans sa grille). La règle « sous la grille » la
#   regarde toujours.
# - Positionnement_9BOX retiré : c'est maintenant une catégorie (« Talents »...), que l'IA ne sait pas
#   lire comme un nombre ; et il se déduit de la performance et de la compétence, déjà regardées.
# - Ajouté : le rang de la performance N-1 (1 = Très en dessous ... 5 = Très au-delà).
# - Ni le Mid ni le ratio grille / marché, que la régression lit pourtant : ils décrivent la grille du
#   métier + niveau, pas la personne. Essayés, ils faisaient remonter surtout les salariés des grilles
#   rares (les plus hauts niveaux), parce qu'elles sont rares, et non parce que leur salaire pose
#   question.
FEATS = ["Fixe_Annuel_MAD", "CompaRatio", "MarketRatio", "Age", "Anciennete", "Competence_N1", "Rang_Performance",
         "Hot_job"]


def entrainer_ia(df: pd.DataFrame, rule_params: dict, random_state: int = 42, feats=None):
    """Entraîne l'Isolation Forest sur les colonnes FEATS et rend le modèle et le tableau qu'il a lu.

    Pourquoi une fonction à part : anomaly_signal_fort.py en a besoin pour expliquer le score. Avec
    les mêmes salariés, les mêmes réglages et le même hasard fixé (random_state), elle redonne
    exactement le même modèle, donc exactement les mêmes scores.

    feats : les colonnes à regarder à la place de FEATS. La détection ne s'en sert pas (elle regarde
    toujours FEATS) ; analyse_diplomes/diplome.py s'en sert pour essayer l'IA avec le diplôme en plus, sans
    rien changer à la détection.
    """
    feats = FEATS if feats is None else list(feats)
    # Une colonne vide pour tout le monde (un fichier sans performance N-1, par exemple) ne dit rien au
    # modèle, et il ne saurait pas la lire : elle est laissée de côté.
    feats = [f for f in feats if f in df and df[f].notna().any()]
    # Le modèle ne sait pas traiter une case vide : on la remplace par la valeur du milieu de sa
    # colonne (la médiane).
    X = df[feats].fillna(df[feats].median())

    # Pourquoi ces deux réglages sont lus dans le fichier de règles : dans l'archive, ils étaient
    # écrits en dur (0.05 et 200), alors que tous les autres seuils se règlent sans toucher au code.
    iso = IsolationForest(
        n_estimators=int(rule_params.get("ml_n_estimators")),
        contamination=float(rule_params.get("ml_contamination")),
        random_state=random_state,
    )
    iso.fit(X)
    return iso, X


def ml_anomaly(df: pd.DataFrame, rule_params: dict, random_state: int = 42, feats=None) -> pd.DataFrame:
    """Calcule un score d'anomalie non supervisé via IsolationForest et rend un NOUVEAU DataFrame
    (celui reçu n'est pas modifié), avec la colonne ML_AnomalyScore en plus.

    Ce que fait le modèle, en clair : il regarde le profil de chaque salarié (salaire, ratios, âge,
    ancienneté et champs RH) et cherche ceux qui ne ressemblent pas aux
    autres. Il découpe les salariés au hasard, encore et encore : un profil très inhabituel se
    retrouve isolé en peu de découpes, un profil banal en demande beaucoup. « Non supervisé » veut
    dire qu'on ne lui a jamais montré d'exemples d'anomalies : il les repère tout seul.

    Le score va de 0 (le profil le plus banal du fichier) à 100 (le plus atypique du fichier). Il est
    recalculé pour chaque fichier : un même score n'a pas le même sens d'un fichier à l'autre.

    Réglages lus dans rule_params (valeur par défaut entre parenthèses) :
    - ml_contamination (0.05) : part d'anomalies que le modèle s'attend à trouver ;
    - ml_n_estimators (200) : nombre d'arbres, c'est-à-dire de découpages au hasard.
    random_state=42 fixe le hasard : on obtient le même score à chaque lancement.
    feats : les colonnes à regarder à la place de FEATS (voir entrainer_ia) ; la détection n'en donne pas.
    """
    # Depuis le 10/11/2026, la détection regarde d'abord l'écart au salaire attendu (ml_methode:
    # ecart_attendu dans config/rules.yaml, voir score_ecart_attendu dans anomaly_signal_regression.py).
    # Pourquoi : sur le banc d'essai (analyse_modeles/banc_essai_ia.py), l'Isolation Forest repère ce qui
    # est RARE (un âge, un salaire de directeur), pas ce qui est MAL PAYÉ ; l'écart au salaire attendu
    # repère 10 fois plus de salariés sous-payés dans leur grille. L'Isolation Forest reste disponible
    # (ml_methode: isolation_forest), et c'est toujours elle qui tourne quand on lui donne des colonnes
    # (feats), comme le fait analyse_diplomes/diplome.py.
    if feats is None and rule_params.get("ml_methode", "isolation_forest") == "ecart_attendu":
        return score_ecart_attendu(df, rule_params)

    df = df.copy()

    iso, X = entrainer_ia(df, rule_params, random_state, feats)
    # score_samples rend un nombre d'autant plus BAS que le profil est atypique : le signe « - »
    # l'inverse, pour que « plus grand » veuille dire « plus atypique ».
    score = -iso.score_samples(X)

    # On ramène le score entre 0 et 100 : 0 pour le plus banal, 100 pour le plus atypique.
    # Si tous les scores sont égaux (aucun profil ne se distingue), tout le monde reçoit 50.
    s_min, s_max = score.min(), score.max()
    if s_max > s_min:
        # np.clip : les minuscules erreurs d'arrondi de l'ordinateur pouvaient donner
        # 100,00000000000001 ; on ramène toute valeur qui dépasse à la limite.
        df["ML_AnomalyScore"] = np.clip(100 * (score - s_min) / (s_max - s_min), 0, 100)
    else:
        df["ML_AnomalyScore"] = 50.0

    return df


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_signal_iforest.py),
# pas quand un autre programme fait « from anomaly_signal_iforest import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_signal_iforest.py).
    projet = Path(__file__).resolve().parent.parent

    # Les réglages : la partie « rules: » du fichier de règles.
    with open(projet / "config" / "rules.yaml", encoding="utf-8") as fichier:
        rule_params = yaml.safe_load(fichier)["rules"]

    # Les étapes dans l'ordre : la sortie de chacune est l'entrée de la suivante.
    # 1. Prétraitement : lecture, doublons, grille, marché, ratios (anomaly_pretraitement.py).
    df = preparer_employes(projet / "input" / "employes.xlsx",
                           projet / "input" / "bands.xlsx",
                           projet / "input" / "market.xlsx")
    # 2. Groupes de collègues et écart PeerZ (anomaly_cohortes.py).
    df = former_cohortes(df, rule_params)
    # 3. Règles : étiquettes, points et motifs (anomaly_regles.py).
    df = apply_rulebook(df, rule_params)
    # 4. Score de l'IA (ce fichier).
    df = ml_anomaly(df, rule_params)
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, en fichier Excel (.xlsx) : il s'ouvre directement, sans souci de
    # séparateur, de virgule décimale ou d'accents.
    sortie = projet / "output" / "signal_iforest" / "employes_signal_iforest.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    # Dans le fichier, les nombres calculés ont 2 chiffres après la virgule. Les calculs gardent toute leur précision.
    df.round(2).to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
