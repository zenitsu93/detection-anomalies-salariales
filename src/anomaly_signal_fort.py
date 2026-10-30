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

from pathlib import Path

import pandas as pd
import yaml

from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import entrainer_ia, ml_anomaly

# Les informations que regarde l'IA, telles qu'on les écrit dans l'explication : nom, facteur,
# décimales, unité. La position dans la grille s'écrit en % (0 % = au Min, 100 % = au Max).
NOMS = {
    "Fixe_Annuel_MAD": ("le salaire", 1, 0, " kMAD"),
    "CompaRatio": ("le CompaRatio", 1, 2, ""),
    "RangePenetration": ("la position dans la grille", 100, 0, " %"),
    "MarketRatio": ("le ratio marché", 1, 2, ""),
    "Age": ("l'âge", 1, 0, " ans"),
    "Anciennete": ("l'ancienneté", 1, 1, " ans"),
    "Competence_N1": ("la note de compétences N-1", 1, 2, ""),
    "Positionnement_9BOX": ("la case 9-Box", 1, 0, ""),
    "Hot_job": ("le Hot job", 1, 0, ""),
}
# Les informations qui disent combien le salarié est payé (voir le choix B dans apply_ml_strong_signal).
PAYE = ["Fixe_Annuel_MAD", "CompaRatio", "RangePenetration", "MarketRatio"]


def texte(valeur, info):
    """La valeur d'une information, écrite à la française : 573.58 -> « 574 kMAD », 3.5 -> « 3,5 »."""
    _, facteur, decimales, unite = NOMS[info]
    nombre = f"{valeur * facteur:,.{decimales}f}".replace(",", " ").replace(".", ",")
    if "," in nombre:
        nombre = nombre.rstrip("0").rstrip(",")
    # « 1 an », « 0,5 an », mais « 2 ans ».
    if unite == " ans" and valeur * facteur < 2:
        unite = " an"
    # Une position hors de la grille (sous 0 % ou au-dessus de 100 %) se lit mal seule : on le dit.
    if info == "RangePenetration" and not 0 <= valeur <= 1:
        unite += ", sous le Min" if valeur < 0 else ", au-dessus du Max"
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


def apply_ml_strong_signal(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Ajoute l'étiquette ML_STRONG_SIGNAL et son explication aux salariés parmi les plus atypiques
    pour l'IA (les 5 % du haut avec ml_strong_signal_percentile = 0.95), qu'une règle se soit
    déclenchée ou non. Ne touche pas à Rule_Score. Rend un NOUVEAU DataFrame (celui reçu n'est pas
    modifié).

    On classe les salariés du score le plus faible au plus élevé, puis on prend le seuil au-dessus
    duquel se trouvent les 5 % du haut (sur 100 salariés, ce serait vers le 95ᵉ). Ceux qui sont
    atypiques surtout parce qu'ils sont payés plus haut que d'habitude sont ensuite retirés : le
    signal touche donc un peu moins de 5 % des salariés.
    """
    percentile = rule_params.get("ml_strong_signal_percentile")

    df = df.copy()

    # Le score à partir duquel on fait partie des plus atypiques.
    seuil = df["ML_AnomalyScore"].quantile(percentile)
    candidats = df.index[df["ML_AnomalyScore"] >= seuil]

    # Pourquoi l'IA trouve chacun d'eux atypique. Le modèle est recréé à l'identique de l'étape IA
    # (mêmes salariés, mêmes réglages, même hasard fixé) : il donne exactement les mêmes scores. Il
    # n'est pas reçu de l'étape précédente, qui ne passe que le tableau des salariés.
    modele, X = entrainer_ia(df, rule_params)
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
            "surtout " + " et ".join(f"{NOMS[c][0]} ({texte(X.at[i, c], c)}, contre {texte(habituel[c], c)} en général)"
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
    df.to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
