#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ANALYSE 2 : LE DIPLÔME DANS L'IA (ISOLATION FOREST)
===================================================

La question : l'IA trouve-t-elle mieux les salaires trop bas si elle regarde aussi le diplôme ?

Ce que fait ce fichier, sans rien changer à la détection : il la lance deux fois, avec l'IA habituelle,
puis avec une IA qui regarde en plus le niveau d'études (son rang, de 0 = secondaire à 7 = BAC+7) et la
catégorie du diplôme (une colonne 0/1 par catégorie trouvée dans le fichier). Il montre :
1. qui entre et qui sort des salariés les plus atypiques pour l'IA, et s'ils sont mieux ou moins bien
   payés. L'IA repère ce qui est RARE, pas forcément ce qui est mal payé : c'est ce qu'il faut vérifier ;
2. le diplôme de ces salariés, comparé à celui de l'ensemble ;
3. le signal fort, les priorités, et les explications de l'IA qui citent le diplôme.

Utilisation, depuis le dossier du projet (ou double-clic sur analyse_diplomes/lancer_analyses.bat) :
      python analyse_diplomes/ia.py
Résultats dans output/analyse_diplomes/ : la page ia_AAAA-MM-JJ_HH-MM-SS.html, et ia.xlsx, la liste des
salariés qui entrent ou sortent des plus atypiques, ou dont la priorité ou le signal fort change.
"""

import numpy as np
import pandas as pd

from commun import (INCONNU, PROJET, TRANCHES, charger, comparer_payes, detection, ecrire_page, pour_cent,
                    resume, salaries, tableau_priorites, virgule)
from anomaly_signal_iforest import FEATS
from anomaly_signal_fort import CATEGORIE


def encoder_categories(df: pd.DataFrame):
    """Ajoute une colonne 0/1 par catégorie de diplôme présente dans le fichier, nommée « Categorie : »
    suivi de la catégorie (c'est ce nom que l'explication de l'IA sait écrire en clair). Rend le tableau
    et la liste des colonnes ajoutées.
    Pourquoi des colonnes 0/1 : une catégorie n'a pas d'ordre (un diplôme de commerce n'est pas « plus »
    qu'un diplôme d'ingénieur), on ne peut donc pas la numéroter. Pourquoi les catégories du fichier et
    pas une liste fixe : si elles sont écrites autrement, une liste fixe ne les reconnaîtrait pas.
    Une catégorie inconnue laisse les cases vides, pas à 0 : « 0 » voudrait dire « on sait qu'il n'a pas
    ce diplôme »."""
    categorie = df["Cat_Ecole_Max"].astype("string").str.strip().str.upper()
    colonnes = []
    for valeur in sorted(categorie.dropna().unique()):
        colonne = CATEGORIE + valeur
        df = df.assign(**{colonne: (categorie == valeur).astype(float).where(categorie.notna())})
        colonnes.append(colonne)
    return df, colonnes


def signal_fort(df):
    """Vrai pour les salariés qui ont le signal fort de l'IA (ML_STRONG_SIGNAL)."""
    return df["Rule_Flags"].fillna("").str.contains("ML_STRONG_SIGNAL")


if __name__ == "__main__":
    rule_params, df = charger()
    df, categories = encoder_categories(df)
    feats_avec = FEATS + ["Rang_Etude_Max"] + categories

    print("Détection avec l'IA habituelle...")
    avant = detection(df, rule_params)
    print("Détection avec le diplôme dans l'IA...")
    apres = detection(df, rule_params, feats=feats_avec)

    # « Les plus atypiques » : la même part que le signal fort (5 % avec ml_strong_signal_percentile = 0.95),
    # avant qu'il ne retire ceux qui le sont surtout parce qu'ils sont bien payés.
    part = 1 - float(rule_params["ml_strong_signal_percentile"])
    top_avant = avant["ML_AnomalyScore"] >= avant["ML_AnomalyScore"].quantile(1 - part)
    top_apres = apres["ML_AnomalyScore"] >= apres["ML_AnomalyScore"].quantile(1 - part)
    entrent, sortent = apres[top_apres & ~top_avant], avant[top_avant & ~top_apres]
    constat1 = (f"Avec le diplôme, {salaries(len(entrent))} sur {virgule(top_apres.sum(), 0)} changent parmi les "
                f"plus atypiques. Entrent : {resume(entrent)}. Sortent : {resume(sortent)}."
                + comparer_payes(entrent, sortent))

    # Le diplôme des plus atypiques, comparé à celui de tous les salariés.
    tranche = df["Tranche_Etude"].fillna(INCONNU)
    ordre = [t for t in TRANCHES + [INCONNU] if (tranche == t).any()]
    parts = pd.DataFrame({
        "Tous les salariés": tranche.value_counts(normalize=True),
        "Les plus atypiques, IA habituelle": tranche[top_avant].value_counts(normalize=True),
        "Les plus atypiques, avec le diplôme": tranche[top_apres].value_counts(normalize=True),
    }).reindex(ordre).fillna(0)
    graphe = [{"type": "bar", "orientation": "h", "name": nom, "y": ordre, "x": (parts[nom] * 100).round(1).tolist(),
               "marker": {"color": couleur}, "text": [pour_cent(v) for v in parts[nom]], "textposition": "outside",
               "hovertemplate": "%{x:.1f} %<extra>" + nom + "</extra>"}
              for nom, couleur in zip(parts.columns, ["#c9ced4", "#5b6b7d", "#e9a21b"])]
    rapport = (parts["Les plus atypiques, avec le diplôme"] / parts["Tous les salariés"]).replace(np.inf, np.nan)
    trop = rapport[rapport >= 1.5].dropna()
    constat2 = ("Avec le diplôme, aucune tranche n'est au moins 1,5 fois plus présente parmi les plus atypiques que "
                "parmi tous les salariés." if trop.empty else
                "Avec le diplôme, " + " ; ".join(f"« {t} » est {virgule(r, 1)} fois plus présente parmi les plus "
                                                 "atypiques que parmi tous les salariés" for t, r in trop.items())
                + ".")

    # Le signal fort et les explications qui citent le diplôme.
    sf_avant, sf_apres = signal_fort(avant), signal_fort(apres)
    constat3 = (f"Signal fort : {salaries(sf_avant.sum())} avec l'IA habituelle, {salaries(sf_apres.sum())} avec le "
                f"diplôme. Le reçoivent en plus : {resume(apres[sf_apres & ~sf_avant])}. Le perdent : "
                f"{resume(avant[sf_avant & ~sf_apres])}." + comparer_payes(apres[sf_apres & ~sf_avant], avant[sf_avant & ~sf_apres]))
    explications = apres.loc[sf_apres, "Explication_IA"].fillna("")
    citent = explications[explications.str.contains("niveau d'études|catégorie de diplôme")]
    constat4 = (f"{virgule(len(citent), 0)} explication{'s' if len(citent) > 1 else ''} du signal fort sur "
                f"{virgule(len(explications), 0)} cite{'nt' if len(citent) > 1 else ''} le diplôme"
                + (" ; les cinq premières :" if len(citent) else "."))
    exemples = "".join(f"<li>{e}</li>" for e in citent.head(5))
    liste_categories = ", ".join(c[len(CATEGORIE):] for c in categories) or "aucune"

    corps = f"""
<p class="lire">Avec le diplôme, l'IA regarde en plus le niveau d'études (son rang, de 0 = secondaire à 7 = BAC+7) et
la catégorie du diplôme, une colonne par catégorie trouvée dans le fichier ({liste_categories}).</p>

<h2>1. Qui entre et qui sort des plus atypiques</h2>
<p class="lire">Les plus atypiques sont les {pour_cent(part)} de salariés qui ont le score IA le plus haut. Ajouter le
diplôme est utile si ceux qui entrent sont plus mal payés (CompaRatio plus bas) que ceux qui sortent.</p>
<p class="constat">{constat1}</p>

<h2>2. Le diplôme des plus atypiques</h2>
<p class="lire">L'IA repère ce qui est rare. Si une tranche de diplôme est beaucoup plus présente parmi les plus
atypiques (barre orange) que parmi tous les salariés (barre grise), l'IA les fait remonter pour leur diplôme, pas
forcément pour leur salaire.</p>
<div id="g" class="graphe"></div>
<p class="constat">{constat2}</p>

<h2>3. Le signal fort et les priorités</h2>
<p class="constat">{constat3}</p>
<p class="lire">Chaque case compte les salariés qui ont la priorité de la ligne avec l'IA habituelle, et celle de la
colonne avec le diplôme. Les cases grises de la diagonale sont ceux qui ne changent pas.</p>
{tableau_priorites(avant, apres)}

<h2>4. Les explications de l'IA qui citent le diplôme</h2>
<p class="constat">{constat4}</p><ul>{exemples}</ul>"""
    graphes = {"g": (graphe, {"barmode": "group", "margin": {"l": 130, "r": 50, "t": 30, "b": 50},
                              "legend": {"orientation": "h", "y": 1.12, "traceorder": "normal"},
                              "xaxis": {"title": {"text": "Part des salariés (%)"}, "gridcolor": "#e6e8eb",
                                        "rangemode": "tozero"},
                              "yaxis": {"autorange": "reversed"}})}
    page = ecrire_page("ia", "Le diplôme dans l'IA", df, corps, graphes)

    # Les salariés qui bougent, avec ce qui permet de juger le changement.
    change = (top_avant != top_apres) | (sf_avant != sf_apres) | (avant["Severity"] != apres["Severity"])
    oui_non = {True: "oui", False: "non"}
    liste = df.loc[change, ["Matricule", "Entite_N1", "Job_Family", "Niveau", "Niveau_Etude_Max", "Cat_Ecole_Max",
                            "Fixe_Annuel_MAD", "CompaRatio"]].assign(
        Score_IA_habituel=avant.loc[change, "ML_AnomalyScore"].round(1),
        Score_IA_avec_diplome=apres.loc[change, "ML_AnomalyScore"].round(1),
        Plus_atypiques_IA_habituelle=top_avant[change].map(oui_non),
        Plus_atypiques_avec_diplome=top_apres[change].map(oui_non),
        Signal_fort_IA_habituelle=sf_avant[change].map(oui_non),
        Signal_fort_avec_diplome=sf_apres[change].map(oui_non),
        Priorite_IA_habituelle=avant.loc[change, "Severity"], Priorite_avec_diplome=apres.loc[change, "Severity"],
        Explication_IA_avec_diplome=apres.loc[change, "Explication_IA"])
    excel = PROJET / "output" / "analyse_diplomes" / "ia.xlsx"
    liste.to_excel(excel, index=False)
    print(f"Page : {page}")
    print(f"Salariés qui bougent ({change.sum()}) : {excel}")
