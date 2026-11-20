# Les six modèles, communs aux notebooks 2_Prediction et 3_Prediction_Par_Cohorte.
#
# | Modèle | Explique       | Avec                    |
# |--------|----------------|-------------------------|
# | M1     | le salaire     | une régression linéaire |
# | M2     | le salaire     | un arbre de décision    |
# | M3     | le Compa-Ratio | une régression linéaire |
# | M4     | le Compa-Ratio | un arbre de décision    |
# | M5     | le salaire     | un gradient boosting    |
# | M6     | le Compa-Ratio | un gradient boosting    |
#
# Tous les réglages (profondeur de l'arbre, logarithme, Mid en plus) viennent de reglages.py.

import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.tree import DecisionTreeRegressor

import reglages


def creer_modeles():
    # Rend les six modèles : pour chacun, ce qu'il explique (en clair), sa cible, et la façon de faire.
    salaire = 'le salaire (en log)' if reglages.LOG_SALAIRE else 'le salaire'
    compa_ratio = 'le Compa-Ratio (en log)' if reglages.LOG_COMPA_RATIO else 'le Compa-Ratio'
    return {
        'M1': (f'{salaire}, par une régression', 'Fixe_Annuel_MAD', LinearRegression()),
        'M2': (f'{salaire}, par un arbre', 'Fixe_Annuel_MAD', DecisionTreeRegressor(max_depth=reglages.PROFONDEUR, random_state=42)),
        'M3': (f'{compa_ratio}, par une régression', 'Compa_Ratio', LinearRegression()),
        'M4': (f'{compa_ratio}, par un arbre', 'Compa_Ratio', DecisionTreeRegressor(max_depth=reglages.PROFONDEUR, random_state=42)),
        # M5 et M6 : un gradient boosting, des centaines de petits arbres qui se corrigent l'un l'autre. Pourquoi en plus de l'arbre
        # seul : un arbre de profondeur 5 ne sait donner que 32 valeurs différentes ; le gradient boosting en donne une par salarié,
        # et il suit des effets qui ne sont pas en ligne droite. random_state : le même résultat à chaque lancement.
        'M5': (f'{salaire}, par un gradient boosting', 'Fixe_Annuel_MAD', HistGradientBoostingRegressor(random_state=42)),
        'M6': (f'{compa_ratio}, par un gradient boosting', 'Compa_Ratio', HistGradientBoostingRegressor(random_state=42)),
    }


def salaire_predit(modele, cible, apprend, verifie, X, df):
    # Le modèle apprend sur les salariés « apprend », puis prédit le salaire (en MAD) des salariés « verifie ».
    # X : les colonnes du modèle. df : le tableau complet, pour le salaire, le Compa-Ratio et le Mid.
    # Un seul résultat, toujours en salaire :
    # - M1, M2 et M5 apprennent le salaire ; s'il est en logarithme, on revient au salaire par l'exponentielle ;
    # - M3, M4 et M6 apprennent le Compa-Ratio ; s'il est en logarithme, on revient au Compa-Ratio par l'exponentielle ;
    #   salaire prédit = Compa-Ratio prédit × Mid.
    # clone : un modèle neuf à chaque fois, qui n'a rien gardé de l'apprentissage d'avant.
    modele = clone(modele)
    if cible == 'Fixe_Annuel_MAD':
        en_plus = [c for c in reglages.EN_PLUS_POUR_LE_SALAIRE if c in df.columns and c not in X.columns]
        if reglages.LOG_SALAIRE:
            X_modele = X.join(np.log(df[en_plus]).add_prefix('Log_'))
            modele.fit(X_modele.loc[apprend], np.log(df.loc[apprend, cible]))
            return np.exp(modele.predict(X_modele.loc[verifie]))
        X_modele = X.join(df[en_plus])
        modele.fit(X_modele.loc[apprend], df.loc[apprend, cible])
        return modele.predict(X_modele.loc[verifie])
    # Les modèles du Compa-Ratio : salaire prédit = Compa-Ratio prédit × Mid
    if reglages.LOG_COMPA_RATIO:
        modele.fit(X.loc[apprend], np.log(df.loc[apprend, cible]))
        return np.asarray(np.exp(modele.predict(X.loc[verifie])) * df.loc[verifie, 'Mid'])
    modele.fit(X.loc[apprend], df.loc[apprend, cible])
    return np.asarray(modele.predict(X.loc[verifie]) * df.loc[verifie, 'Mid'])


def metriques(cible, y_vrai, y_pred, mid):
    # MAE et RMSE : sur le salaire, en MAD, pour les six modèles.
    # R² : un seul par modèle, calculé sur ce que le modèle prédit. Le salaire pour M1, M2 et M5 ;
    # le Compa-Ratio pour M3, M4 et M6 (le salaire divisé par le Mid redonne le Compa-Ratio).
    return {'MAE (MAD)': mean_absolute_error(y_vrai, y_pred),
            'RMSE (MAD)': mean_squared_error(y_vrai, y_pred) ** 0.5,
            'R²': r2_score(y_vrai, y_pred) if cible == 'Fixe_Annuel_MAD' else r2_score(y_vrai / mid, y_pred / mid)}
