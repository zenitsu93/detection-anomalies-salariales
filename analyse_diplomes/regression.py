#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ANALYSE 3 : LE DIPLÔME DANS LA RÉGRESSION QUI PRÉDIT UN SALAIRE
==============================================================

La question : le salaire prédit par la régression (src/anomaly_signal_regression.py, le repère de l'aide
à la décision) est-il plus juste si le modèle connaît aussi le diplôme ?

Ce que fait ce fichier, sans rien changer au modèle de l'aide à la décision :
- il coupe les salariés en 5 paquets ; le modèle apprend sur 4 et on regarde de combien il se trompe sur
  le 5e, qu'il n'a pas vu ; on recommence en changeant de paquet, puis on refait tout 10 fois avec
  d'autres paquets : 50 essais. Pourquoi tant d'essais : avec un seul tirage, une petite amélioration
  peut venir du hasard ;
- il le fait pour quatre modèles : sans le diplôme ; avec la tranche de diplôme ; avec la tranche et la
  catégorie ; et un témoin, avec la tranche et la catégorie MÉLANGÉES AU HASARD entre salariés du même
  métier et du même niveau. Le témoin dit combien on gagne rien qu'en ajoutant des colonnes qui ne
  veulent rien dire : le diplôme n'aide vraiment que s'il fait nettement mieux que lui ;
- il montre de combien le diplôme change le salaire prédit, tout le reste égal.

Utilisation, depuis le dossier du projet (ou double-clic sur analyse_diplomes/lancer_analyses.bat) :
      python analyse_diplomes/regression.py
Résultat dans output/analyse_diplomes/ : la page regression_AAAA-MM-JJ_HH-MM-SS.html.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import RepeatedKFold

from commun import charger, ecrire_page, virgule
from anomaly_signal_regression import COLONNES, tableau_x

AVEC_TRANCHE = COLONNES + ["Tranche_Etude"]
AVEC_TOUT = COLONNES + ["Tranche_Etude", "Cat_Ecole_Max"]


def essais(df, colonnes):
    """Les 50 essais d'un modèle. Pour chacun : l'erreur moyenne en kMAD, la part du salaire expliquée
    (de 0 à 1) et la largeur de la fourchette qui contient le vrai salaire 9 fois sur 10, en % du salaire
    prédit. Les paquets sont les mêmes pour tous les modèles (random_state=42) : on les compare sur les
    mêmes salariés mis de côté."""
    X = tableau_x(df, colonnes)
    Y = np.log(df["Fixe_Annuel_MAD"]).to_numpy()
    lignes = []
    for apprend, verifie in RepeatedKFold(n_splits=5, n_repeats=10, random_state=42).split(X):
        predit = LinearRegression().fit(X.iloc[apprend], Y[apprend]).predict(X.iloc[verifie])
        erreur = Y[verifie] - predit
        bas, haut = np.quantile(erreur, [0.05, 0.95])
        lignes.append({"mae": np.mean(np.abs(np.exp(Y[verifie]) - np.exp(predit))),
                       "r2": 1 - np.sum(erreur ** 2) / np.sum((Y[verifie] - Y[verifie].mean()) ** 2),
                       "largeur": (np.exp(haut) - np.exp(bas)) * 100})
    return pd.DataFrame(lignes)


def melanger(df):
    """Le témoin : la tranche et la catégorie de diplôme mélangées au hasard entre salariés du même métier
    et du même niveau. Le diplôme garde la même répartition dans chaque métier + niveau, mais n'a plus
    aucun lien avec le salaire de la personne."""
    hasard = np.random.default_rng(42)
    df = df.copy()
    colonnes = ["Tranche_Etude", "Cat_Ecole_Max"]
    for lignes in df.groupby(["Job_Family", "Niveau"]).groups.values():
        df.loc[lignes, colonnes] = df.loc[lignes, colonnes].to_numpy()[hasard.permutation(len(lignes))]
    return df


def effets(df, colonne):
    """De combien le salaire prédit change, en %, quand on donne à TOUS les salariés la même valeur de la
    colonne, comparé à la valeur la plus fréquente, tout le reste égal. Rend la valeur de référence et
    les écarts des autres valeurs.
    Pourquoi la valeur la plus fréquente comme référence : elle existe toujours, quelle que soit la façon
    dont le fichier écrit les diplômes (un nom écrit en dur pourrait ne pas y être)."""
    valeurs = df[colonne].value_counts()
    reference = valeurs.index[0]
    X = tableau_x(df, AVEC_TOUT)
    modele = LinearRegression().fit(X, np.log(df["Fixe_Annuel_MAD"]))

    def predit(valeur):
        return modele.predict(tableau_x(df.assign(**{colonne: valeur}), AVEC_TOUT).reindex(columns=X.columns, fill_value=0))

    base = predit(reference)
    ecarts = pd.Series({v: (np.mean(np.exp(predit(v) - base)) - 1) * 100 for v in valeurs.index[1:]}, dtype=float)
    return reference, ecarts


def signe(x):
    """2.31 -> « +2,3 % » ; -0.04 -> « 0,0 % »."""
    texte = virgule(x, 1)
    return f"{'+' if texte != '0,0' and x > 0 else ''}{texte} %"


if __name__ == "__main__":
    _, df = charger()
    # Un salarié sans salaire utilisable ne peut pas servir à apprendre un salaire.
    df = df[df["Fixe_Annuel_MAD"] > 0].reset_index(drop=True)

    print("Essais des quatre modèles (50 essais chacun)...")
    resultats = {"Sans le diplôme": essais(df, COLONNES),
                 "Avec la tranche de diplôme": essais(df, AVEC_TRANCHE),
                 "Avec la tranche et la catégorie": essais(df, AVEC_TOUT),
                 "Témoin : diplômes mélangés au hasard": essais(melanger(df), AVEC_TOUT)}

    lignes = "".join(f"<tr><th>{nom}</th><td>{virgule(r['mae'].mean(), 1)}</td>"
                     f"<td>{virgule(r['r2'].mean(), 2)}</td><td>± {virgule(r['largeur'].mean() / 2, 0)} %</td></tr>"
                     for nom, r in resultats.items())
    sans, avec, temoin = (resultats[n] for n in ["Sans le diplôme", "Avec la tranche et la catégorie",
                                                 "Témoin : diplômes mélangés au hasard"])
    gain, gain_temoin = sans["mae"].mean() - avec["mae"].mean(), sans["mae"].mean() - temoin["mae"].mean()
    mieux = (avec["mae"] < sans["mae"]).mean()
    # Le verdict suit les chiffres : le diplôme n'aide que s'il gagne plus que le témoin ET fait mieux que le
    # modèle sans lui dans au moins 9 essais sur 10 (sinon, son gain peut venir du hasard des paquets).
    if gain > max(gain_temoin, 0) and mieux >= 0.9:
        verdict = (f"Le diplôme rend le salaire prédit plus juste : il fait mieux que le modèle sans lui dans "
                   f"{virgule(mieux * 100, 0)} % des essais, et mieux que des diplômes tirés au hasard.")
    elif gain <= max(gain_temoin, 0):
        verdict = "Le diplôme ne rend pas le salaire prédit plus juste : il ne fait pas mieux que des diplômes tirés au hasard."
    else:
        verdict = (f"Le diplôme ne rend pas le salaire prédit nettement plus juste : il ne fait mieux que dans "
                   f"{virgule(mieux * 100, 0)} % des essais.")
    constat1 = (f"Erreur moyenne : {virgule(sans['mae'].mean(), 1)} kMAD sans le diplôme, "
                f"{virgule(avec['mae'].mean(), 1)} kMAD avec, {virgule(temoin['mae'].mean(), 1)} kMAD avec le témoin. "
                f"{verdict}")

    graphes, phrases, blocs = {}, [], []
    for cle, colonne, nom, couleur in [("t", "Tranche_Etude", "la tranche de diplôme", "#e9a21b"),
                                       ("c", "Cat_Ecole_Max", "la catégorie de diplôme", "#5b6b7d")]:
        reference, ecarts = effets(df, colonne)
        if ecarts.empty:
            phrases.append(f"Pour {nom}, une seule valeur est connue ({reference}) : rien à comparer.")
            continue
        # Les écarts sont déjà écrits au bout des barres : la phrase ne donne que le plus grand.
        plus_grand = ecarts.abs().idxmax()
        phrases.append(f"Pour {nom}, le plus grand écart avec « {reference} » est celui de « {plus_grand} » : "
                       f"{signe(ecarts[plus_grand])}.")
        # Pourquoi l'axe va au moins de -5 % à +5 % : sinon Plotly l'ajuste aux barres, et un écart de 0,3 %
        # remplirait toute la largeur, comme s'il était énorme. Un écart plus grand élargit l'axe.
        etendue = max(5.0, float(ecarts.abs().max()) * 1.25)
        graphes[cle] = ([{"type": "bar", "orientation": "h", "y": [str(v) for v in ecarts.index],
                          "x": ecarts.round(1).tolist(), "marker": {"color": couleur},
                          "text": [signe(e) for e in ecarts], "textposition": "outside",
                          "hovertemplate": "%{x:.1f} %<extra></extra>"}],
                        {"showlegend": False, "margin": {"l": 200, "r": 60, "t": 40, "b": 50},
                         "title": {"text": f"{nom[0].upper()}{nom[1:]}, par rapport à « {reference} »",
                                   "font": {"size": 14}, "x": 0},
                         "xaxis": {"title": {"text": "Écart de salaire prédit (%)"}, "gridcolor": "#e6e8eb",
                                   "zerolinecolor": "#5b6b7d", "range": [-etendue, etendue]}})
        blocs.append(f'<div id="{cle}" class="graphe" style="height: 300px"></div>')

    corps = f"""
<h2>1. Les erreurs du modèle, sans et avec le diplôme</h2>
<p class="lire">Chaque modèle est essayé 50 fois : il apprend sur 80 % des salariés, puis on mesure son erreur sur
les 20 % qu'il n'a pas vus. Le <b>témoin</b> a des diplômes mélangés au hasard : il montre ce qu'on gagne avec des
colonnes qui ne veulent rien dire. Le diplôme n'aide que s'il fait nettement mieux que lui.</p>
<table><tr><th>Modèle</th><th>Erreur moyenne (kMAD)</th><th>Part du salaire expliquée (0 = rien, 1 = tout)</th>
<th>Marge d'erreur (9 fois sur 10)</th></tr>{lignes}</table>
<p class="constat">{constat1}</p>

<h2>2. De combien le diplôme change le salaire prédit</h2>
<p class="lire">À métier, niveau, ancienneté, âge, notes et Hot job égaux, par rapport à la valeur la plus fréquente.
Une barre proche de 0 veut dire que le diplôme ne change presque rien au salaire prédit.</p>
{"".join(blocs)}
<p class="constat">{" ".join(phrases)}</p>"""
    page = ecrire_page("regression", "Le diplôme dans la régression qui prédit un salaire", df, corps, graphes)
    print(f"Page : {page}")
