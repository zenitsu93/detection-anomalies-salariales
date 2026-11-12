#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SIGNAL FORT DE L'IA : UN SIXIÈME SIGNAL POUR LES PROFILS TRÈS ATYPIQUES
=======================================================================

Les cinq règles regardent le salaire sous un angle précis (grille, CompaRatio, marché, collègues,
salaire minimum). L'IA, elle, regarde tout le profil d'un coup (ML_AnomalyScore). Ce fichier fait
remonter ce qu'elle voit comme un sixième signal : les salariés parmi les plus atypiques pour l'IA
reçoivent l'étiquette ML_STRONG_SIGNAL et un motif, en plus des signaux des règles.

Ce signal n'ajoute aucun point : Rule_Score ne change pas. Le score de l'IA compte déjà dans le
score général (ml_weight dans config/rules.yaml) ; lui donner aussi des points le compterait deux
fois.

Il dit aussi POURQUOI l'IA trouve le salarié atypique (colonne Explication_IA), par exemple :
« surtout l'âge (24 ans, contre 40 ans en général) et l'ancienneté (15 ans, contre 6 ans en général) ».
Et un salarié atypique surtout parce qu'il est payé plus haut que d'habitude ne reçoit pas le
signal : depuis le comité du 15/10/2026, être payé au-dessus n'est pas un cas à traiter.

Il prend en entrée le DataFrame rendu par anomaly_signal_iforest.py et rend ce DataFrame complété.

Utilisation :
- depuis Python :
      from anomaly_signal_fort import apply_ml_strong_signal
      df = apply_ml_strong_signal(df, rule_params)
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_signal_fort.py
  Le DataFrame est enregistré dans output/signal_fort/employes_signal_fort.xlsx, à ouvrir avec Excel.
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from anomaly_pretraitement import ORDRE_PERFORMANCE, RANG_NIVEAU_ETUDE, preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import entrainer_ia, ml_anomaly
from anomaly_signal_regression import COLONNES as COLONNES_REGRESSION, NOMS as NOMS_REGRESSION, POSTE, \
    _donnees, _robuste, contributions

# Les informations que regarde l'IA, telles qu'on les écrit dans l'explication : nom, facteur,
# décimales, unité. Depuis le 10/11/2026, l'IA ne regarde plus la position dans la grille ni la case
# 9-Box (voir FEATS dans anomaly_signal_iforest.py) : leurs lignes sont retirées, celle de la
# performance N-1 ajoutée.
NOMS = {
    "Fixe_Annuel_MAD": ("le salaire", 1, 0, " kMAD"),
    "CompaRatio": ("le CompaRatio", 1, 2, ""),
    "MarketRatio": ("le ratio marché", 1, 2, ""),
    "Age": ("l'âge", 1, 0, " ans"),
    "Anciennete": ("l'ancienneté", 1, 1, " ans"),
    "Competence_N1": ("la note de compétences N-1", 1, 2, ""),
    "Rang_Performance": ("la performance N-1", 1, 0, ""),
    "Hot_job": ("le Hot job", 1, 0, ""),
    # Pas regardé par la détection : seulement quand analyse_diplomes/diplome.py essaie l'IA avec le diplôme.
    "Rang_Etude_Max": ("le niveau d'études", 1, 0, ""),
}
# Le début du nom des colonnes 0/1 de catégorie de diplôme que fabrique analyse_diplomes/diplome.py, par
# exemple « Categorie : DIPLOME D'INGENIEUR ». Pourquoi pas une liste fixe dans NOMS : les catégories
# sont celles écrites dans le fichier des salariés, qu'on ne connaît pas à l'avance.
CATEGORIE = "Categorie : "

# Le rang d'un niveau d'études écrit en toutes lettres : 6 -> « BAC+5 ». Pour un rang que partagent deux
# niveaux, on garde le premier de la table (BAC+5 plutôt que BAC+6, BAC+7 plutôt que l'expertise comptable).
NIVEAU_DU_RANG = {}
for _niveau, _rang in RANG_NIVEAU_ETUDE.items():
    NIVEAU_DU_RANG.setdefault(_rang, _niveau)


def nom(info):
    """Le nom d'une information dans l'explication : « l'âge », « la catégorie de diplôme « … » »."""
    if info.startswith(CATEGORIE):
        return f"la catégorie de diplôme « {info[len(CATEGORIE):]} »"
    return NOMS[info][0]
# Les informations qui disent combien le salarié est payé (voir le choix B dans apply_ml_strong_signal).
PAYE = ["Fixe_Annuel_MAD", "CompaRatio", "MarketRatio"]


def texte(valeur, info):
    """La valeur d'une information, écrite à la française : 573.58 -> « 574 kMAD », 3.5 -> « 3,5 »."""
    # Le niveau d'études s'écrit en toutes lettres (« BAC+5 ») plutôt qu'avec son rang (« 6 »). Le niveau
    # habituel (la médiane de tous les salariés) peut tomber entre deux rangs, par exemple 5,5 : on écrit
    # alors « entre BAC+4 et BAC+5 ».
    if info == "Rang_Etude_Max":
        bas, haut = NIVEAU_DU_RANG[math.floor(valeur)], NIVEAU_DU_RANG[math.ceil(valeur)]
        return bas if bas == haut else f"entre {bas} et {haut}"
    # La performance N-1 aussi, en libellé (« A l'objectif ») plutôt qu'avec son rang (3), entre
    # guillemets ; la performance habituelle peut tomber entre deux rangs, comme le niveau d'études.
    if info == "Rang_Performance":
        bas, haut = ORDRE_PERFORMANCE[math.floor(valeur) - 1], ORDRE_PERFORMANCE[math.ceil(valeur) - 1]
        return f"« {bas} »" if bas == haut else f"entre « {bas} » et « {haut} »"
    # Une catégorie de diplôme s'écrit « oui » ou « non » plutôt que 1 ou 0. La valeur habituelle peut
    # tomber entre les deux (0,5) quand il y a autant de oui que de non : on écrit alors « un sur deux ».
    if info.startswith(CATEGORIE):
        return "oui" if valeur == 1 else "non" if valeur == 0 else "un sur deux"
    _, facteur, decimales, unite = NOMS[info]
    nombre = f"{valeur * facteur:,.{decimales}f}".replace(",", " ").replace(".", ",")
    if "," in nombre:
        nombre = nombre.rstrip("0").rstrip(",")
    # « 1 an », « 0,5 an », mais « 2 ans ».
    if unite == " ans" and valeur * facteur < 2:
        unite = " an"
    return nombre + unite


def poids_des_infos(modele, X: pd.DataFrame, lignes) -> pd.DataFrame:
    """Pour chaque salarié de lignes, de combien son score d'atypie BAISSE quand on remet UNE de ses
    informations à la valeur habituelle (la médiane de tous les salariés), les autres restant telles
    quelles. Rend un tableau : une ligne par salarié, une colonne par information.

    C'est comme chercher quel symptôme compte le plus : si remettre l'âge à la normale fait beaucoup
    baisser le score, c'est surtout l'âge qui rend le salarié atypique pour l'IA. On interroge le vrai
    modèle, sans rien installer de plus. Limite : quand c'est une COMBINAISON qui est inhabituelle
    (jeune, mais avec beaucoup d'ancienneté), aucune information seule ne fait tout baisser.
    """
    habituel = X.median()
    # score_samples est d'autant plus bas que le profil est atypique : le « - » le remet dans le bon sens.
    depart = -modele.score_samples(X.loc[lignes])
    baisses = {}
    for info in X.columns:
        normal = X.loc[lignes].copy()
        normal[info] = habituel[info]
        baisses[info] = depart + modele.score_samples(normal)
    return pd.DataFrame(baisses, index=lignes)


def apply_ml_strong_signal(df: pd.DataFrame, rule_params: dict, feats=None) -> pd.DataFrame:
    """Ajoute l'étiquette ML_STRONG_SIGNAL et son explication aux salariés parmi les plus atypiques
    pour l'IA (les 5 % du haut avec ml_strong_signal_percentile = 0.95), qu'une règle se soit
    déclenchée ou non. Ne touche pas à Rule_Score. Rend un NOUVEAU DataFrame (celui reçu n'est pas
    modifié).

    On classe les salariés du score le plus faible au plus élevé, puis on prend le seuil au-dessus
    duquel se trouvent les 5 % du haut (sur 100 salariés, ce serait vers le 95ᵉ). Ceux qui sont
    atypiques surtout parce qu'ils sont payés plus haut que d'habitude sont ensuite retirés : le
    signal touche donc un peu moins de 5 % des salariés.
    """
    if feats is None and rule_params.get("ml_methode", "isolation_forest") == "ecart_attendu":
        return signal_ecart_attendu(df, rule_params)

    percentile = rule_params.get("ml_strong_signal_percentile")

    df = df.copy()

    # Le score à partir duquel on fait partie des plus atypiques.
    seuil = df["ML_AnomalyScore"].quantile(percentile)
    candidats = df.index[df["ML_AnomalyScore"] >= seuil]

    # Pourquoi l'IA trouve chacun d'eux atypique. Le modèle est recréé à l'identique de l'étape IA
    # (mêmes salariés, mêmes réglages, même hasard fixé) : il donne exactement les mêmes scores. Il
    # n'est pas reçu de l'étape précédente, qui ne passe que le tableau des salariés.
    # feats : les colonnes que regarde l'IA, si on lui en donne d'autres que FEATS (voir entrainer_ia).
    # La détection n'en donne pas ; analyse_diplomes/diplome.py, si : l'explication doit alors être tirée du
    # même modèle que le score.
    modele, X = entrainer_ia(df, rule_params, feats=feats)
    habituel = X.median()
    baisses = poids_des_infos(modele, X, candidats)

    df["Explication_IA"] = ""
    fort = []
    for i in candidats:
        b = baisses.loc[i]
        # Les deux informations qui pèsent le plus. Une information dont la remise à la normale ne fait
        # pas baisser le score n'y est pour rien : elle n'est pas citée.
        infos = b[b > 0].nlargest(2).index.tolist()
        # Choix B, après la décision du comité du 15/10/2026 : si ce qui pèse le plus est un salaire ou
        # un ratio PLUS HAUT que d'habitude, le salarié est atypique parce qu'il est bien payé. Ce n'est
        # pas un cas à traiter : pas de signal fort. Un salaire trop BAS, lui, garde le signal.
        if infos and infos[0] in PAYE and X.at[i, infos[0]] > habituel[infos[0]]:
            continue
        fort.append(i)
        df.at[i, "Explication_IA"] = (
            "surtout " + " et ".join(f"{nom(c)} ({texte(X.at[i, c], c)}, contre {texte(habituel[c], c)} en général)"
                                     for c in infos)
            if infos else "aucune information ne ressort seule : c'est leur combinaison qui est inhabituelle")

    # Le signal et son motif s'ajoutent à ceux des règles, avec les mêmes séparateurs que dans
    # anomaly_regles.py (« ; » et « & »). Pour un salarié sans aucune règle déclenchée, il n'y avait
    # rien avant : on retire le séparateur resté en tête. Pourquoi le motif reprend l'explication :
    # avant, il disait seulement « Profil atypique détecté par le modèle ML », sans dire pourquoi.
    df.loc[fort, "Rule_Flags"] += ";ML_STRONG_SIGNAL"
    df["Rule_Flags"] = df["Rule_Flags"].str.lstrip(";")
    df.loc[fort, "Reason_Principale"] += " & Profil atypique selon l'IA : " + df.loc[fort, "Explication_IA"]
    df["Reason_Principale"] = df["Reason_Principale"].str.removeprefix(" & ")

    return df


def pour_cent(x):
    """-0.173 -> « 17 % » (sans signe : la phrase dit « de moins » ou « de plus »)."""
    return f"{abs(x) * 100:.0f} %"


def kmad(x):
    """245.3 -> « 245 kMAD »."""
    return f"{x:,.0f}".replace(",", " ") + " kMAD"


def signal_ecart_attendu(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Le signal ML_STRONG_SIGNAL quand l'IA regarde l'écart au salaire attendu (ml_methode:
    ecart_attendu). Le reçoivent les salariés payés au moins ml_signal_z écarts habituels sous le salaire
    attendu pour leur poste ET leur profil (Z_Attendu <= -2 par défaut : sous une loi normale, 2 salariés
    sur 100 seulement). Pourquoi un seuil fixe plutôt que « les 5 % du haut » : sans anomalie, personne ne
    devrait recevoir le signal ; avec beaucoup d'anomalies, toutes doivent le recevoir.

    Explication_IA dit de combien et pourquoi, en termes métier, par exemple : « payé 17 % de moins que
    le salaire attendu pour son profil (245 kMAD, 9 fois sur 10 entre 215 et 280 kMAD) ; ce qui relève
    l'attendu : l'ancienneté (15 ans, +6 %) et la performance N-1 (« Très au-delà », +5 %) ». Les
    effets cités sont ceux du profil, comparé au salarié moyen ; le poste (métier, niveau, grille) n'est
    pas cité, puisque la grille dit déjà ce qu'il paie.
    Pas de tri « payé au-dessus » à faire ici (choix B de apply_ml_strong_signal) : seul un salaire SOUS
    l'attendu peut recevoir le signal."""
    seuil = float(rule_params.get("ml_signal_z", 2.0))
    df = df.copy()
    df["Explication_IA"] = ""
    fort = df.index[df["Z_Attendu"] <= -seuil]
    if len(fort):
        colonnes = [c for c in COLONNES_REGRESSION if c in df and df[c].notna().any()]
        # Le même modèle que le salaire attendu (appris sur tous, en robuste) sert à dire ce qui pèse :
        # il est une somme d'effets, si bien que chaque effet se lit exactement.
        X, Y = _donnees(df, colonnes)
        modele, garde = _robuste(X, Y)
        reg = {"modele": modele, "colonnes": colonnes, "colonnes_X": list(X.columns), "moyenne_X": X[garde].mean()}
        effets = contributions(X.loc[X.index.intersection(fort)], reg)
        effets = effets[[c for c in effets.columns if c not in POSTE]]
        for i in fort:
            ligne = df.loc[i]
            phrase = (f"payé {pour_cent(ligne.Ecart_Attendu)} de moins que le salaire attendu pour son profil "
                      f"({kmad(ligne.Salaire_Attendu)}, 9 fois sur 10 entre {kmad(ligne.Attendu_Bas)} "
                      f"et {kmad(ligne.Attendu_Haut)})")
            if i in effets.index:
                hausses = effets.loc[i][effets.loc[i] > 0.01].nlargest(2)
                if len(hausses):
                    phrase += " ; ce qui relève l'attendu : " + " et ".join(
                        f"{NOMS_REGRESSION.get(c, c)} ({valeur_profil(ligne, c)}, +{pour_cent(np.expm1(v))})"
                        for c, v in hausses.items())
            df.at[i, "Explication_IA"] = phrase

    # Mêmes séparateurs que dans anomaly_regles.py (« ; » et « & »), comme pour l'Isolation Forest.
    df.loc[fort, "Rule_Flags"] += ";ML_STRONG_SIGNAL"
    df["Rule_Flags"] = df["Rule_Flags"].str.lstrip(";")
    df.loc[fort, "Reason_Principale"] += " & IA : " + df.loc[fort, "Explication_IA"]
    df["Reason_Principale"] = df["Reason_Principale"].str.removeprefix(" & ")
    return df


def valeur_profil(ligne, colonne):
    """La valeur d'une colonne du profil, écrite pour l'explication : « 15 ans », « « Très au-delà » »."""
    valeur = ligne[colonne]
    if colonne == "Rang_Etude_Max":
        return NIVEAU_DU_RANG.get(valeur, "inconnu") if pd.notna(valeur) else "inconnu"
    if colonne in NOMS:
        return texte(valeur, colonne)
    return f"« {valeur} »" if pd.notna(valeur) else "inconnu"


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_signal_fort.py),
# pas quand un autre programme fait « from anomaly_signal_fort import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_signal_fort.py).
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
    # 4. Score de l'IA (anomaly_signal_iforest.py).
    df = ml_anomaly(df, rule_params)
    # 5. Signal fort de l'IA (ce fichier).
    df = apply_ml_strong_signal(df, rule_params)
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, en fichier Excel (.xlsx) : il s'ouvre directement, sans souci de
    # séparateur, de virgule décimale ou d'accents.
    sortie = projet / "output" / "signal_fort" / "employes_signal_fort.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    # Dans le fichier, les nombres calculés ont 2 chiffres après la virgule. Les calculs gardent toute leur précision.
    df.round(2).to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
