#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LES GROUPES DE COLLÈGUES (« COHORTES ») : former les groupes et mesurer l'écart de chaque salarié
================================================================================================

1. À quoi sert ce fichier
-------------------------

Pour savoir si un salaire est anormal, le programme le compare, entre autres, aux salaires des
collègues COMPARABLES : les personnes qui ont le même grade, le même métier et une ancienneté proche.
Un tel groupe de collègues comparables s'appelle une « cohorte ».

Ce fichier fait deux choses :
- il FORME les groupes : il décide, pour chaque salarié, à quel groupe de collègues on le compare ;
- il MESURE l'écart de chaque salarié par rapport à son groupe (la colonne PeerZ).
Il prend en entrée le DataFrame rendu par anomaly_pretraitement.py, et rend ce DataFrame complété pour
chaque salarié de son groupe et des statistiques de ce groupe (taille, salaire du milieu,
moyenne...). Voir la recette former_cohortes, plus bas.

Ce DataFrame est ensuite l'entrée d'anomaly_regles.py : c'est là que l'écart aux collègues (PeerZ)
déclenche l'alerte PEER_OUTLIER et ajoute des points au score, avec les autres règles.


2. La règle, en une phrase
--------------------------

Chaque salarié est comparé au groupe de collègues LE PLUS PRÉCIS qui compte AU MOINS 15 personnes,
et ce groupe est toujours pris EN ENTIER.

(15 est la valeur de cohort_min_size, dans config/rules.yaml. Pourquoi un minimum ? Parce que
comparer quelqu'un à 2 ou 3 personnes ne veut rien dire : il suffit qu'une seule d'entre elles soit
très bien ou très mal payée pour tout fausser.)

Pour chaque salarié, on essaie ces groupes, dans cet ordre (réglable dans cohort_widening_steps,
dans config/rules.yaml) :
1. même grade + même métier + même tranche d'ancienneté (0-2 ans, 3-5 ans, 6-12 ans, 13-20 ans,
   plus de 20 ans) ;
2. même grade + même métier, toutes anciennetés confondues ;
3. même grade seulement, tous métiers confondus.
On prend le premier qui compte au moins 15 personnes.


3. Pourquoi cette règle remplace l'ancienne
-------------------------------------------

L'ancienne version tournait en boucle : elle cherchait les groupes trop petits, leur collait une
étiquette plus large, recomptait, et recommençait. Il fallait suivre un compteur d'étapes, un
indicateur « ça progresse encore », et des étiquettes de longueurs différentes qui cohabitaient. On
ne pouvait pas prévoir le résultat sans dérouler la boucle à la main.

Surtout, elle n'élargissait les petits groupes qu'ENTRE EUX (les « restes »), sans jamais rattacher
une personne au groupe complet de ses collègues. Des débutants trop peu nombreux dans leur métier
n'étaient donc jamais comparés aux autres personnes de leur métier : ils étaient mis avec les
débutants d'autres métiers (parfois bien mieux payés), dans un groupe qui pouvait rester sous le
minimum, et sans aucun message.


4. Comment vérifier ou déboguer
-------------------------------

- Lancer ce fichier tout seul, depuis le dossier du projet : « python src/anomaly_cohortes.py »
  prépare les vrais fichiers du dossier input/ (avec anomaly_pretraitement.py) et forme les groupes.
  Les 10 premières lignes s'affichent, et le DataFrame complet est enregistré dans
  output/cohortes/cohortes_salaries.csv, à ouvrir avec Excel.
- Dans un éditeur de code, poser un point d'arrêt dans la boucle « for position, niveau in ... » de
  la recette former_cohortes, et regarder trois choses à chaque tour :
  cle (le nom du groupe de chaque salarié à ce niveau), taille (le nombre de personnes de ce groupe),
  et choisis (vrai pour les salariés qui reçoivent leur groupe à ce niveau).
"""


import sys

import numpy as np
import pandas as pd
from pathlib import Path

import yaml
from anomaly_pretraitement import preparer_employes



# -----------------------------------------------------------------------------
# L'écart d'un salarié par rapport à son groupe
# -----------------------------------------------------------------------------

def robust_zscore(values: pd.Series) -> pd.Series:
    """Recette : mesurer, pour chaque salarié d'un groupe, à quel point son salaire s'écarte de
    celui des autres"""
    # On lit les salaires comme des nombres (un salaire illisible devient une case vide).
    x = pd.to_numeric(values, errors="coerce")
    # Le salaire du milieu du groupe (la médiane).
    med = x.median()
    # L'écart habituel : de combien chaque salaire s'éloigne du milieu (abs enlève le signe moins),
    # puis le milieu de ces éloignements.
    mad = (x - med).abs().median()
    # Cas particulier : l'écart habituel vaut 0 (ou ne peut pas être calculé).
    if mad == 0 or np.isnan(mad):
        # Pourquoi (correction) : quand plus de la moitié d'un groupe a exactement le même salaire
        # (fréquent avec des grilles), l'écart médian (MAD) vaut 0. L'ancien code renvoyait alors 0
        # pour tout le monde : un salaire très différent des autres n'était jamais repéré. On se
        # rabat maintenant sur l'écart-type classique.
        # Pourquoi ne pas utiliser l'écart-type tout le temps ? La méthode par la médiane résiste
        # mieux aux salaires extrêmes (un seul très gros salaire ne fausse pas tout le groupe). On ne
        # s'en passe que dans ce cas précis, où elle ne peut rien mesurer.
        # (L'écart-type est l'autre façon classique de mesurer l'écart habituel, à partir de la
        # moyenne cette fois.)
        std = x.std()
        if pd.notna(std) and std > 0:
            return (x - x.mean()) / std
        # Pourquoi .where(x.notna()) : un salarié sans salaire recevait un écart de 0, c'est-à-dire
        # "parfaitement dans la norme". Il reste maintenant vide ("inconnu").
        return pd.Series(0.0, index=x.index).where(x.notna())
    # Cas normal : l'éloignement de chaque salaire divisé par l'écart habituel. Le nombre 0,6745 est
    # un chiffre fixe qui met ce calcul à la même échelle que l'écart-type : ainsi, « 2 » veut dire
    # la même chose avec les deux méthodes.
    return 0.6745 * (x - med) / mad


# -----------------------------------------------------------------------------
# Former les groupes et mesurer l'écart de chaque salarié
# -----------------------------------------------------------------------------

# Les noms lisibles des colonnes qui définissent les groupes, pour écrire le niveau retenu en clair
# (par exemple « grade + métier » au lieu de « Grade|Job_Family »).
NOMS_LISIBLES = {"Grade": "grade", "Job_Family": "métier", "Anciennete_Bucket": "tranche d'ancienneté"}


def former_cohortes(df: pd.DataFrame, rule_params: dict) -> pd.DataFrame:
    """Recette : donner à chaque salarié son groupe de collègues, et mesurer son écart par rapport à ce
    groupe (la règle est expliquée en haut de ce fichier).

    Ce qu'on lui donne :
    - df : le DataFrame des salariés rendu par preparer_employes (anomaly_pretraitement.py) ;
    - rule_params : les réglages lus dans le fichier de règles (config/rules.yaml).

    Ce qu'elle rend : le DataFrame des salariés, COMPLÉTÉ des colonnes ci-dessous. C'est une copie : le
    DataFrame df qu'on lui donne n'est pas modifié. Colonnes ajoutées :
    - Niveau_Cohorte : le niveau de groupe retenu, écrit en clair, par exemple « grade + métier » ;
    - Cohort_Key : le nom du groupe retenu, par exemple « 3|FINANCE|6-12 » ou « 3|FINANCE » ;
    - Cohort_Size : le nombre de personnes dans ce groupe ;
    - Cohort_Median : le salaire du milieu du groupe (la médiane) ;
    - Cohort_Mean : le salaire moyen du groupe ;
    - Cohort_STD : l'écart habituel des salaires du groupe autour de la moyenne (l'écart-type) ;
    - Cohort_P25 et Cohort_P75 : les salaires en dessous desquels se trouvent 25 % et 75 % des
      personnes du groupe ;
    - PeerZ : l'écart du salarié par rapport à son groupe (recette robust_zscore, juste au-dessus)."""
    # Les niveaux de groupe, du plus précis au plus large, lus dans le fichier de règles
    # (cohort_widening_steps). S'ils n'y sont pas, on prend ceux-ci. Chaque niveau est une liste de
    # noms de colonnes séparés par « | » : « Grade|Job_Family » veut dire « même grade et même métier ».
    default_steps = [
        "Grade|Job_Family|Anciennete_Bucket",
        "Grade|Job_Family",
        "Grade"
    ]
    steps = rule_params.get("cohort_widening_steps", default_steps)
    # La taille minimale d'un groupe, lue dans le fichier de règles (15 si elle n'y est pas).
    # « int » veut dire « nombre entier ».
    min_size = int(rule_params.get("cohort_min_size", 15))

    # Le DataFrame rendu est une copie du DataFrame des salariés, avec toutes ses colonnes (« .copy() » :
    # df ne sera pas modifié). Au départ, personne n'a encore de groupe : on ajoute les colonnes des
    # groupes, vides (np.nan veut dire « case vide »). Niveau_Cohorte et Cohort_Key contiendront du
    # texte (dtype=object).
    cohortes = df.copy()
    for colonne in ["Niveau_Cohorte", "Cohort_Key"]:
        cohortes[colonne] = pd.Series(np.nan, index=df.index, dtype=object)
    for colonne in ["Cohort_Size", "Cohort_Median", "Cohort_Mean", "Cohort_STD", "Cohort_P25", "Cohort_P75", "PeerZ"]:
        cohortes[colonne] = np.nan

    # On essaie les niveaux un par un, du plus précis au plus large. « enumerate » donne à la fois le
    # numéro du niveau (position : 0, 1, 2) et le niveau lui-même.
    for position, niveau in enumerate(steps):
        # Les colonnes qui définissent le groupe à ce niveau, par exemple ["Grade", "Job_Family"].
        colonnes = niveau.split("|")
        # Le nom du groupe de chaque salarié à ce niveau : ses valeurs dans ces colonnes, collées avec
        # des « | », par exemple « 3|FINANCE|6-12 ». (astype(str) écrit chaque valeur en texte ; une
        # case vide devient le texte « nan », et les personnes concernées forment leur propre groupe.)
        cle = df[colonnes].astype(str).agg("|".join, axis=1)
        # Les salariés rangés par groupe COMPLET à ce niveau (tous ceux qui ont le même nom de groupe).
        groupes = df.groupby(cle)
        # Pour chaque salarié, le nombre de personnes de son groupe à ce niveau. « transform » recopie
        # le résultat de chaque groupe sur chacune de ses lignes.
        taille = groupes["Matricule"].transform("count")

        # Qui reçoit son groupe à ce niveau ?
        # - sans_groupe : les salariés qui n'en ont pas encore reçu à un niveau plus précis ;
        # - dernier_niveau : vrai si c'est le niveau le plus large (le dernier de la liste) ;
        # - choisis : les salariés sans groupe dont le groupe à ce niveau compte au moins min_size
        #   personnes. Au dernier niveau, on prend TOUS ceux qui restent, même si leur groupe est
        #   petit, car il n'existe rien de plus large (un avertissement le signale à la fin).
        sans_groupe = cohortes["Cohort_Key"].isna()
        dernier_niveau = position == len(steps) - 1
        choisis = sans_groupe if dernier_niveau else sans_groupe & (taille >= min_size)
        # Personne à placer à ce niveau : on passe directement au niveau suivant (« continue »).
        if not choisis.any():
            continue

        # Pour les salariés choisis, on remplit leurs colonnes (« cohortes.loc[choisis, ...] » veut
        # dire « seulement sur les lignes des salariés choisis »). Toutes les statistiques sont
        # calculées sur le groupe ENTIER à ce niveau, même si certains de ses membres ont reçu, eux, un
        # groupe plus précis : c'est ce qui fait que chacun est comparé à tous ses collègues du groupe.
        salaires = groupes["Fixe_Annuel_MAD"]
        # Le niveau retenu, écrit en clair (par exemple « grade + métier »).
        cohortes.loc[choisis, "Niveau_Cohorte"] = " + ".join(NOMS_LISIBLES.get(c, c) for c in colonnes)
        # Le nom et la taille du groupe retenu.
        cohortes.loc[choisis, "Cohort_Key"] = cle[choisis]
        cohortes.loc[choisis, "Cohort_Size"] = taille[choisis]
        # Le salaire du milieu, la moyenne et l'écart-type du groupe.
        cohortes.loc[choisis, "Cohort_Median"] = salaires.transform("median")[choisis]
        cohortes.loc[choisis, "Cohort_Mean"] = salaires.transform("mean")[choisis]
        cohortes.loc[choisis, "Cohort_STD"] = salaires.transform("std")[choisis]
        # Les salaires en dessous desquels se trouvent 25 % et 75 % du groupe (np.nanpercentile ignore
        # les cases vides).
        cohortes.loc[choisis, "Cohort_P25"] = salaires.transform(lambda x: np.nanpercentile(x, 25))[choisis]
        cohortes.loc[choisis, "Cohort_P75"] = salaires.transform(lambda x: np.nanpercentile(x, 75))[choisis]
        # L'écart de chaque salarié par rapport à son groupe entier (recette robust_zscore, plus haut).
        cohortes.loc[choisis, "PeerZ"] = salaires.transform(robust_zscore)[choisis]

    # À ce stade, tout le monde a un groupe : la taille redevient un nombre entier (15 et non 15,0).
    cohortes["Cohort_Size"] = cohortes["Cohort_Size"].astype(int)
    # On prévient si certains salariés n'ont trouvé qu'un groupe trop petit, même au niveau le plus
    # large (par exemple un grade qui ne compte que 8 personnes en tout) : leur comparaison aux
    # collègues est peu fiable.
    trop_petits = cohortes["Cohort_Size"] < min_size
    if trop_petits.any():
        print(
            f"[WARN] {int(trop_petits.sum())} salarié(s) dans un groupe de collègues de moins de {min_size} "
            "personnes, même au niveau le plus large - comparaison aux collègues peu fiable pour eux.",
            file=sys.stderr,
        )
    # On rend le DataFrame des salariés, complété de leur groupe.
    return cohortes


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_cohortes.py),
# pas quand un autre programme fait « from anomaly_cohortes import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_cohortes.py).
    projet = Path(__file__).resolve().parent.parent

    # Le DataFrame des salariés prétraité (anomaly_pretraitement.py).
    salaries = preparer_employes(projet / "input" / "employes.csv",
                                 projet / "input" / "bands.csv",
                                 projet / "input" / "market.csv")
    # Les réglages : la partie « rules: » du fichier de règles.
    with open(projet / "config" / "rules.yaml", encoding="utf-8") as fichier:
        reglages = yaml.safe_load(fichier)["rules"]

    df = former_cohortes(salaries, reglages)
    print(df.head(10).to_string(index=False))

    # Le DataFrame complet, pour Excel : séparateur « ; », virgule décimale, et encodage utf-8-sig
    # (pour qu'Excel affiche bien les accents).
    sortie = projet / "output" / "cohortes" / "cohortes_salaries.csv"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(sortie, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
