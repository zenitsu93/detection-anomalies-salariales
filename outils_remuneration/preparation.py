# La préparation du tableau, commune aux trois notebooks du dossier.
#
# Deux fonctions :
# - preparer_tableau() : charge les fichiers, lance la détection, calcule les ratios, retire les anomalies
#   puis les valeurs aberrantes. Elle rend LE tableau des salariés sur lequel tout le monde travaille ;
# - choisir_colonnes(df) : ne garde que les deux cibles et les colonnes de la liste COLONNES, en chiffres.
#
# Tous les réglages viennent de reglages.py.

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import yaml

import reglages

# Le dossier de ce fichier : tout ce dont les notebooks ont besoin est dedans
ICI = Path(__file__).resolve().parent

# Les fonctions de la détection d'anomalies sont dans le sous-dossier detection/
sys.path.append(str(ICI / 'detection'))
from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import ml_anomaly
from anomaly_signal_fort import apply_ml_strong_signal
from anomaly_score_general import aggregate_risk
from anomaly_recommandations import recommendations

# Les deux variables à prédire : le salaire fixe et le Compa-Ratio
CIBLES = ['Fixe_Annuel_MAD', 'Compa_Ratio']

# Le dossier où les notebooks écrivent leurs fichiers Excel. Il est créé s'il n'existe pas.
RESULTATS = ICI / 'resultats'
RESULTATS.mkdir(exist_ok=True)

# Les rangs de la performance et du niveau d'études, pour les passer en chiffres
RANG_PERFORMANCE = {"Très en dessous": 1, "Proche de l'objectif": 2, "A l'objectif": 3, "Supérieur à l'objectif": 4, "Très au-delà": 5}
# BAC MAX = le bac ou moins. Les trois derniers sont les anciens noms (fichiers d'avant le 23/11/2026) :
# le secondaire et le bac valent BAC MAX, l'expertise comptable vaut BAC+7.
RANG_ETUDE = {'BAC MAX': 1, 'BAC+1': 2, 'BAC+2': 3, 'BAC+3': 4, 'BAC+4': 5, 'BAC+5': 6, 'BAC+6': 6, 'BAC+7': 7,
              'SECONDAIRE': 1, 'BAC': 1, 'EXPERTISE COMPTABLE': 7}


def outliers(colonne):
    # True pour les valeurs au-delà des moustaches : à plus de 1,5 fois la largeur de la boîte
    q1, q3 = colonne.quantile(0.25), colonne.quantile(0.75)
    return (colonne < q1 - 1.5 * (q3 - q1)) | (colonne > q3 + 1.5 * (q3 - q1))


def preparer_tableau():
    # Rend un objet « tableau » avec :
    # - tableau.df : les salariés gardés, ceux sur lesquels on travaille ;
    # - tableau.detection : le résultat complet de la détection, pour tous les salariés ;
    # - tableau.priorites : les priorités de la détection, de la plus grave à la moins grave ;
    # - tableau.retires : les anomalies retirées (priorités de A_RETIRER) ;
    # - tableau.avant_outliers : le tableau juste avant le retrait des valeurs aberrantes (pour les boîtes à moustaches) ;
    # - tableau.ecartes : les salariés écartés pour une valeur aberrante, avec la raison ;
    # - tableau.regles : les réglages de la détection (config/rules.yaml).

    # 1. Les réglages de la détection (seuils, poids, priorités) : le fichier config/rules.yaml du dossier
    with open(ICI / 'config' / 'rules.yaml', encoding='utf-8') as fichier:
        regles = yaml.safe_load(fichier)['rules']
    # « Outlier positif » s'ajoute à la fin : un salarié sans alerte, payé au-dessus du Max de sa grille
    priorites = list(regles['prioritization_buckets'])[::-1] + ['Outlier positif']

    # 2. La détection, étape après étape (les fichiers du sous-dossier detection/).
    #    Elle lit les trois fichiers et donne à chaque salarié sa grille, son marché, un score et une priorité.
    dossier = (ICI / reglages.DOSSIER).resolve()
    print(f"Données lues dans : {dossier}")
    detection = preparer_employes(str(dossier / 'employes.xlsx'), str(dossier / 'bands.xlsx'), str(dossier / 'market.xlsx'))
    for etape in (former_cohortes, apply_rulebook, ml_anomaly, apply_ml_strong_signal, aggregate_risk, recommendations):
        detection = etape(detection, regles)
    print(f"{len(detection)} salariés analysés par la détection.")

    # 3. Les anomalies à retirer : les salariés des priorités de A_RETIRER
    inconnues = [p for p in reglages.A_RETIRER if p not in priorites]
    if inconnues:
        print(f"Priorité inconnue, ignorée : {inconnues}. Les priorités possibles : {priorites}")
    retires = detection[detection['Severity'].isin(reglages.A_RETIRER)]

    # 4. Le tableau de la régression part de celui de la détection
    df = detection.copy()

    # 5. Les ratios
    df['Compa_Ratio'] = df['Fixe_Annuel_MAD'] / df['Mid']
    df['Ratio_Grille_Marche'] = df['Mid'] / df['Median']
    if 'Age' in df.columns and 'Anciennete' in df.columns:
        df['Age_Embauche'] = df['Age'] - df['Anciennete']
    # Une division par zéro donne « infini » : on remet la case à vide
    df = df.replace([np.inf, -np.inf], np.nan)
    # Un ratio négatif ou nul est impossible (salaire à 0 ou négatif) : case vidée aussi
    for c in ['Compa_Ratio', 'Ratio_Grille_Marche']:
        df.loc[df[c] <= 0, c] = np.nan

    # 6. Un salarié sans Compa-Ratio (pas de grille, ou pas de salaire) ne peut pas servir : on le retire
    sans_cible = df['Compa_Ratio'].isna()
    df = df[~sans_cible].reset_index(drop=True)
    print(f"{len(df)} salariés gardés, {int(sans_cible.sum())} retirés (pas de grille ou pas de salaire).")

    # 7. Une colonne vide, ou qui a la même valeur pour tout le monde, ne peut rien expliquer : on la retire.
    #    Les nombres à virgule sont arrondis au millième : un écart d'arrondi (0,6600001) n'est pas une vraie différence.
    inutiles = [c for c in df.columns if (df[c].round(3) if pd.api.types.is_float_dtype(df[c]) else df[c]).nunique() <= 1]
    df = df.drop(columns=inutiles)
    if inutiles:
        print(f"Colonnes vides ou identiques pour tous, retirées : {inutiles}")

    # 8. Les anomalies sortent du tableau, repérées par leur matricule
    anomalie = df['Matricule'].isin(retires['Matricule'])
    df = df[~anomalie]
    print(f"Retrait (A_RETIRER = {reglages.A_RETIRER}) : {int(anomalie.sum())} salariés retirés, {len(df)} restent.")

    # 9. Les valeurs aberrantes. Pour chaque ligne, on note pourquoi elle doit partir (une ligne peut avoir plusieurs raisons).
    avant_outliers = df
    raison = pd.Series('', index=df.index)
    if reglages.ENLEVER:
        for c in [c for c in reglages.COLONNES_RETRAIT if c in df.columns]:
            raison[outliers(df[c])] += f'outlier {c} ; '
    raison = raison.str.rstrip(' ;')
    # Les lignes écartées sont rangées dans « ecartes », avec la raison juste après le matricule
    ecartes = df[raison != ''].copy()
    ecartes.insert(1, 'Raison', raison[ecartes.index])
    # On les retire du tableau. Aucune valeur n'est modifiée.
    df = df[raison == '']
    print(f"Valeurs aberrantes (ENLEVER = {reglages.ENLEVER}) : {len(ecartes)} écartées, {len(df)} salariés restent.")

    return SimpleNamespace(df=df, detection=detection, priorites=priorites, retires=retires,
                           avant_outliers=avant_outliers, ecartes=ecartes, regles=regles)


def choisir_colonnes(df):
    # Rend le tableau « donnees » : les deux cibles et les colonnes de la liste COLONNES, toutes en chiffres,
    # sans case vide. C'est lui qui sert à la matrice de corrélation et aux modèles.

    # 1. On part du tableau complet (df) et on ne garde que les deux cibles et les colonnes de la liste.
    #    df lui-même n'est pas modifié.
    absentes = [c for c in reglages.COLONNES if c not in df.columns]
    if absentes:
        print(f"Colonnes de la liste ignorées (absentes du fichier, ou identiques pour tous les salariés) : {absentes}")
    if [c for c in reglages.COLONNES if c in CIBLES]:
        print(f"Ignoré : {[c for c in reglages.COLONNES if c in CIBLES]}. Ce sont les variables à prédire : ce serait donner la réponse aux modèles.")
    donnees = df[CIBLES + [c for c in reglages.COLONNES if c in df.columns and c not in CIBLES]].copy()

    # 2. L'ancienneté en buckets : une seule colonne, le numéro du bucket (1 = le moins d'ancienneté)
    if reglages.BUCKETS_ANCIENNETE and 'Anciennete' in df.columns:
        donnees['Bucket_Anciennete'] = pd.cut(df['Anciennete'], [-np.inf] + reglages.BORNES_ANCIENNETE + [np.inf], labels=False, right=False) + 1
        print(f"Salariés par bucket d'ancienneté : {donnees['Bucket_Anciennete'].dropna().astype(int).value_counts().sort_index().to_dict()}")
    elif reglages.BUCKETS_ANCIENNETE:
        print("Pas de buckets d'ancienneté : le fichier n'a pas de colonne Anciennete.")

    # 3. La performance et le niveau d'études passent en rang, pour apparaître dans la matrice.
    # Une performance inconnue ou un niveau d'études non déterminé restent vides : rien n'est mis à leur
    # place (demandes du 25/11/2026). Avant, ils prenaient le rang médian.
    # Si la plupart des libellés du fichier ne sont pas ceux prévus, on ne force rien : la colonne reste
    # en texte et n'est pas utilisée.
    for colonne, rangs in [('Performance_N1', RANG_PERFORMANCE), ('Niveau_Etude_Max', RANG_ETUDE)]:
        if colonne in donnees.columns and donnees[colonne].isin(list(rangs)).mean() > 0.5:
            donnees[colonne] = donnees[colonne].map(rangs)
            if donnees[colonne].isna().any():
                # Pourquoi le dire : mettre le rang médian à la place, c'était inventer une information.
                # Pourquoi ces salariés sortent plus bas, alors que la détection du projet les garde : la régression
                # en ligne droite ne sait pas lire une case vide, et les six modèles sont jugés sur les mêmes salariés.
                quoi = 'Performance N-1 inconnue' if colonne == 'Performance_N1' else "Niveau d'études non déterminé"
                print(f"{quoi} pour {int(donnees[colonne].isna().sum())} salariés : "
                      "rien n'est mis à la place, ils sortent plus bas avec les cases vides.")

    # 4. Les colonnes restées en texte (le métier, par exemple) ne sont pas utilisées :
    #    les modèles ne lisent que des chiffres.
    en_texte = list(donnees.select_dtypes(exclude='number').columns)
    if en_texte:
        print(f"Colonnes en texte non utilisées : {en_texte}")
        donnees = donnees.drop(columns=en_texte)

    # 5. Un salarié qui a une case vide dans une des colonnes choisies sort : le modèle ne sait pas lire une case vide
    vides = donnees.select_dtypes('number').isna().any(axis=1)
    donnees = donnees[~vides]
    print(f"{len(donnees)} salariés pour la suite ({int(vides.sum())} retirés pour une case vide dans une des colonnes choisies).")
    print(f"{donnees.shape[1] - len(CIBLES)} colonnes pour les modèles : {[c for c in donnees.columns if c not in CIBLES]}")
    return donnees
