#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PRÉTRAITEMENT : PRÉPARER LE TABLEAU DES SALARIÉS
================================================

Ce fichier lit les trois fichiers d'entrée (salariés, grille interne « bands », marché) et rend le
DataFrame des salariés prétraité : une ligne par salarié, avec sa fourchette de grille, la médiane
du marché et ses ratios. C'est le DataFrame sur lequel l'analyse va travailler.
Le diplôme de chaque salarié (son niveau d'études le plus élevé et la catégorie de ce diplôme) est lu
dans ses propres colonnes du fichier des salariés, s'il les a. Ces colonnes sont facultatives : sans
elles, tout se passe comme avant.

C'est la première étape : il n'a besoin d'aucun autre fichier du projet. Le DataFrame qu'il rend est
l'entrée d'anomaly_cohortes.py, dont la sortie est à son tour l'entrée d'anomaly_regles.py, puis
d'anomaly_signal_iforest.py, puis d'anomaly_signal_regression.py.

Utilisation :
- depuis Python :
      from anomaly_pretraitement import preparer_employes
      df = preparer_employes("input/employes.xlsx", "input/bands.xlsx", "input/market.xlsx")
- en ligne de commande, depuis le dossier du projet :
      python src/anomaly_pretraitement.py
  Le DataFrame est enregistré dans output/pretraitement/employes_pretraites.xlsx, à ouvrir avec Excel.
"""

from pathlib import Path

import numpy as np
import pandas as pd

# Le rang de chaque niveau d'études, du moins élevé (0) au plus élevé (7). Pourquoi un nombre : un
# texte se trie dans l'ordre alphabétique, si bien que SECONDAIRE passerait après BAC+7 et EXPERTISE
# COMPTABLE ; avec le rang, Excel trie les niveaux d'études dans le bon ordre. C'est la même table que dans le
# notebook des diplômes : BAC+6 compte comme BAC+5 (il est saisi surtout sur des masters) et l'expertise
# comptable comme BAC+7. Un niveau absent de la table (« NON DETERMINE », par exemple) n'a pas de rang :
# le salarié n'est pas compté comme « sans diplôme », son niveau est simplement inconnu.
RANG_NIVEAU_ETUDE = {
    "SECONDAIRE": 0,
    "BAC": 1,
    "BAC+1": 2,
    "BAC+2": 3,
    "BAC+3": 4,
    "BAC+4": 5,
    "BAC+5": 6,
    "BAC+6": 6,
    "BAC+7": 7,
    "EXPERTISE COMPTABLE": 7,
}

# Les cinq libellés de la performance N-1 (colonne Performance_N1), du plus bas au plus haut.
ORDRE_PERFORMANCE = ["Très en dessous", "Proche de l'objectif", "A l'objectif", "Supérieur à l'objectif", "Très au-delà"]
# Les six catégories du positionnement 9-Box (colonne Positionnement_9BOX), de la meilleure à celle qui
# demande une décision. Le positionnement est lu tel quel dans le fichier, jamais recalculé ; cet ordre
# sert seulement à le présenter (listes de choix de l'aide à la décision).
ORDRE_9BOX = ["Hauts Potentiels", "Talents", "Performers", "A repositionner", "A développer", "Décisions requises"]

# Les deux colonnes du diplôme dans employes.xlsx, et les autres noms acceptés pour chacune. Pourquoi
# plusieurs noms : le notebook des diplômes les appelle niveau_max et categorie_diplome_max dans ses
# calculs, puis Niveau_Etude_Max et Cat_Ecole_Max à l'export ; ses colonnes sont reconnues sous l'un ou
# l'autre nom, sans tenir compte des majuscules, des espaces ni des « _ ».
NOMS_DIPLOMES = {
    "Niveau_Etude_Max": ["niveauetudemax", "niveaumax"],
    "Cat_Ecole_Max": ["catecolemax", "categoriediplomemax"],
}


def rang_etude(niveaux: pd.Series) -> pd.Series:
    """Le rang (0 à 7) de chaque niveau d'études, ou une case vide si le niveau n'est pas dans
    RANG_NIVEAU_ETUDE. Les espaces et les majuscules ne comptent pas : « Bac + 5 » vaut « BAC+5 »."""
    table = {niveau.replace(" ", ""): rang for niveau, rang in RANG_NIVEAU_ETUDE.items()}
    texte = niveaux.astype("string").str.replace(r"\s+", "", regex=True).str.upper()
    return texte.map(table).astype(float)


def tranche_etude(rangs: pd.Series) -> pd.Series:
    """Range chaque rang dans une des trois tranches : « BAC+2 ou moins » (rangs 0 à 3), « BAC+3 ou
    BAC+4 » (4 et 5), « BAC+5 et plus » (6 et 7). Case vide si le rang est inconnu.
    Pourquoi trois tranches et pas dix niveaux : pour comparer des salariés par diplôme, il faut assez de
    monde dans chaque groupe ; les niveaux rares (secondaire, BAC+1, doctorat) feraient des groupes de
    quelques personnes. Et une erreur d'un cran dans la saisie (BAC+4 au lieu de BAC+5) change moins
    souvent de tranche que de niveau."""
    tranche = pd.Series(np.nan, index=rangs.index, dtype=object)
    tranche[rangs <= 3] = "BAC+2 ou moins"
    tranche[rangs.between(4, 5)] = "BAC+3 ou BAC+4"
    tranche[rangs >= 6] = "BAC+5 et plus"
    return tranche


def ajouter_diplomes(df: pd.DataFrame, nom_fichier: str = "employes.xlsx") -> pd.DataFrame:
    """Lit le diplôme de chaque salarié dans ses propres colonnes du fichier des salariés, et en tire
    deux colonnes calculées. Les quatre colonnes du diplôme sont alors :
    - Niveau_Etude_Max : son niveau d'études le plus élevé, tel qu'écrit dans le fichier (« BAC+5 ») ;
    - Cat_Ecole_Max : la catégorie de ce diplôme (« DIPLOME D'INGENIEUR »...), telle qu'écrite ;
    - Rang_Etude_Max (calculée) : le rang de ce niveau, de 0 à 7 (voir RANG_NIVEAU_ETUDE) ;
    - Tranche_Etude (calculée) : sa tranche, « BAC+2 ou moins », « BAC+3 ou BAC+4 » ou « BAC+5 et plus ».
    Pourquoi plus de fichier des diplômes à part : le fichier des salariés porte désormais le diplôme de
    chacun, sur sa ligne. Il n'y a donc plus de matricules à faire correspondre d'un fichier à l'autre,
    ni de doublons de diplômes à départager.
    Une colonne absente du fichier est ajoutée vide : les étapes suivantes la trouvent quand même, et la
    détection tourne comme avant. Un salarié dont la case est vide a un diplôme inconnu.
    nom_fichier : le nom du fichier des salariés, seulement pour les messages.
    Ce qu'il a trouvé (colonnes manquantes, niveaux non reconnus) est rangé dans df.attrs, une petite
    fiche que pandas accroche au tableau ; message_diplomes la lit pour l'écrire dans le terminal.
    """
    # Chaque colonne est reconnue sous un de ses noms acceptés, puis prend son nom habituel.
    def simple(nom_colonne):
        return "".join(str(nom_colonne).split()).replace("_", "").lower()

    renommage = {}
    for nom_habituel, autres in NOMS_DIPLOMES.items():
        # Pourquoi passer si le nom habituel est déjà là : si le fichier a à la fois « Niveau_Etude_Max »
        # et « niveau_max », c'est la première qui compte ; renommer la seconde ferait deux colonnes du
        # même nom, et la suite ne saurait pas laquelle lire.
        if nom_habituel in df.columns:
            continue
        trouvee = next((c for c in df.columns if simple(c) in autres and c not in renommage), None)
        if trouvee is not None:
            renommage[trouvee] = nom_habituel
    df = df.rename(columns=renommage)
    manquantes = [c for c in NOMS_DIPLOMES if c not in df.columns]
    for colonne in manquantes:
        df[colonne] = np.nan

    df["Rang_Etude_Max"] = rang_etude(df["Niveau_Etude_Max"])
    df["Tranche_Etude"] = tranche_etude(df["Rang_Etude_Max"])
    # Les niveaux écrits qui n'ont pas de rang, hors « NON DETERMINE » : une faute de frappe se voit ainsi
    # dans le terminal au lieu de passer en « niveau inconnu » sans rien dire.
    sans_rang = df.loc[df["Niveau_Etude_Max"].notna() & df["Rang_Etude_Max"].isna(), "Niveau_Etude_Max"]
    df.attrs["diplomes"] = {"fichier": nom_fichier, "manquantes": manquantes,
                            "non_reconnus": sorted(set(sans_rang.astype(str)) - {"NON DETERMINE"})}
    return df


def message_diplomes(df: pd.DataFrame) -> str:
    """Une phrase, pour le terminal, qui dit combien de salariés ont un niveau d'études connu. Pourquoi :
    si les colonnes du diplôme manquent ou sont mal nommées dans le fichier des salariés, rien ne le
    montrerait dans les résultats, à part des colonnes vides.
    """
    def nombre(n):
        return f"{n:,}".replace(",", " ")

    attendues = list(NOMS_DIPLOMES)
    # Pourquoi une fiche par défaut : un tableau qui ne sort pas de ajouter_diplomes n'a pas de fiche ; on
    # le traite alors comme un fichier sans colonnes du diplôme.
    bilan = df.attrs.get("diplomes", {"fichier": "employes.xlsx", "manquantes": attendues, "non_reconnus": []})
    if bilan["manquantes"] == attendues:
        return (f"Pas de colonnes du diplôme dans {bilan['fichier']} ({' et '.join(attendues)}) : "
                "elles restent vides.")
    connus = int(df["Rang_Etude_Max"].notna().sum())
    # « salarié » ou « salariés » selon le nombre : « 1 salarié », mais « 2 salariés ».
    texte = (f"Niveau d'études connu pour {nombre(connus)} salarié{'' if connus == 1 else 's'} "
             f"sur {nombre(len(df))}.")
    if bilan["manquantes"]:
        texte += f" Il manque la colonne {bilan['manquantes'][0]} dans {bilan['fichier']} : elle reste vide."
    if bilan["non_reconnus"]:
        texte += f" Niveaux non reconnus, comptés comme inconnus : {', '.join(bilan['non_reconnus'])}."
    return texte


def bucket_anciennete(x: object) -> str:
    """Range l'ancienneté (en années) dans une tranche : 0-2, 3-5, 6-12, 13-20 ou >20.
    Rend « NA » (inconnue) si l'ancienneté est vide.
    """
    try:
        val = float(x)
    except Exception:
        return "NA"
    if not np.isfinite(val) or val < 0:
        return "NA"
    if val <= 2:
        return "0-2"
    if val <= 5:
        return "3-5"
    if val <= 12:
        return "6-12"
    if val <= 20:
        return "13-20"
    return ">20"


def preparer_employes(chemin_employes, chemin_bands, chemin_market) -> pd.DataFrame:
    """Lit les fichiers d'entrée et rend le DataFrame des salariés prétraité.

    Étapes :
    1. Lire les trois fichiers Excel (.xlsx).
    2. Retirer les doublons : matricule en double chez les salariés, métier + niveau en double dans la
       grille et le marché (le premier est gardé).
    3. Ajouter la tranche d'ancienneté de chaque salarié (Anciennete_Bucket).
    4. Ajouter à chaque salarié la fourchette de sa grille (Min, Mid, Max) et la médiane du marché
       (Market_Median), retrouvées grâce à son métier (Job_Family) et son niveau (Niveau).
    5. Calculer les ratios :
       - CompaRatio = salaire / Mid : 1 veut dire « payé au milieu de la fourchette » ;
       - RangePenetration = (salaire - Min) / (Max - Min) : 0 veut dire « au Min », 1 « au Max » ;
       - MarketRatio = salaire / médiane du marché : 1 veut dire « payé comme le marché » ;
       - Ratio_Grille_Marche = Mid / médiane du marché : 1 veut dire « la grille paie comme le marché ».
    6. Lire le niveau d'études de chaque salarié dans ses colonnes du diplôme, s'il y en a
       (ajouter_diplomes).
    7. Donner un rang à la performance N-1 (Rang_Performance), de 1 à 5, pour l'IA.
    """
    # 1. Lecture des trois fichiers. Ce sont des fichiers Excel : pas de séparateur ni d'encodage à
    # préciser, les nombres arrivent déjà comme des nombres.
    emp = pd.read_excel(chemin_employes)
    bands = pd.read_excel(chemin_bands)
    market = pd.read_excel(chemin_market)

    # 2. Doublons, dans les trois fichiers : on garde toujours le premier.
    cles = ["Job_Family", "Niveau"]
    # Salariés : un même matricule présent deux fois.
    emp = emp.drop_duplicates(subset="Matricule")
    # Grille et marché : un même métier + niveau présent deux fois. Sinon, chaque salarié concerné
    # serait recopié deux fois dans le DataFrame à l'étape 4.
    bands = bands.drop_duplicates(subset=cles)
    market = market.drop_duplicates(subset=cles)

    # 3. Tranche d'ancienneté
    # salarié aux collègues d'ancienneté proche.
    emp["Anciennete_Bucket"] = emp["Anciennete"].apply(bucket_anciennete)

    # 4. Grille et marché, retrouvés par métier + niveau.
    grille = bands[cles + ["Min", "Mid", "Max"]]
    marche = market[cles + ["Median"]].rename(columns={"Median": "Market_Median"})
    # how="left" : on garde tous les salariés, même ceux dont le métier + niveau n'existe pas dans la
    # grille ou le marché (leurs colonnes Min, Mid, Max ou Market_Median restent alors vides).
    df = emp.merge(grille, on=cles, how="left").merge(marche, on=cles, how="left")

    # 5. Ratios.
    # Pourquoi replace(0, np.nan) : un Mid, un écart Max - Min ou une médiane du marché égal à 0
    # ferait une division par zéro (un ratio « infini »). Le ratio reste vide à la place.
    df["CompaRatio"] = df["Fixe_Annuel_MAD"] / df["Mid"].replace(0, np.nan)
    df["RangePenetration"] = (df["Fixe_Annuel_MAD"] - df["Min"]) / (df["Max"] - df["Min"]).replace(0, np.nan)
    df["MarketRatio"] = df["Fixe_Annuel_MAD"] / df["Market_Median"].replace(0, np.nan)
    # Ratio grille / marché = Mid / médiane du marché : 1,10 veut dire que la grille du métier + niveau
    # paie 10 % de plus que le marché. Il ne dépend pas du salaire : c'est la régression qui le lit
    # (anomaly_signal_regression.py).
    df["Ratio_Grille_Marche"] = df["Mid"] / df["Market_Median"].replace(0, np.nan)

    # 6. Niveau d'études, lu dans le fichier des salariés lui-même. Pourquoi seulement maintenant, et pas
    # à la lecture : le rang et la tranche se calculent sur le tableau final, et le nom du fichier sert
    # aux messages du terminal.
    df = ajouter_diplomes(df, Path(chemin_employes).name)

    # 7. Rang de la performance N-1 : 1 = « Très en dessous » ... 5 = « Très au-delà ». Pourquoi un
    # rang : l'IA (anomaly_signal_iforest.py) ne lit que des nombres. Un libellé absent de
    # ORDRE_PERFORMANCE, une case vide ou une colonne absente donnent un rang vide.
    rangs = {libelle: i + 1 for i, libelle in enumerate(ORDRE_PERFORMANCE)}
    df["Rang_Performance"] = df["Performance_N1"].map(rangs) if "Performance_N1" in df else np.nan

    return df


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/anomaly_pretraitement.py),
# pas quand un autre programme fait « from anomaly_pretraitement import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/anomaly_pretraitement.py).
    projet = Path(__file__).resolve().parent.parent

    df = preparer_employes(projet / "input" / "employes.xlsx",
                           projet / "input" / "bands.xlsx",
                           projet / "input" / "market.xlsx")
    print(df.head(10).to_string(index=False))
    print("\n" + message_diplomes(df))

    # Le DataFrame complet, en fichier Excel (.xlsx) : il s'ouvre directement, sans souci de
    # séparateur, de virgule décimale ou d'accents.
    sortie = projet / "output" / "pretraitement" / "employes_pretraites.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    # Dans le fichier, les nombres calculés ont 2 chiffres après la virgule. Les calculs gardent toute leur précision.
    df.round(2).to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
