#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PRÉTRAITEMENT : PRÉPARER LE TABLEAU DES SALARIÉS
================================================

Ce fichier lit les trois fichiers d'entrée (salariés, grille interne « bands », marché) et rend le
DataFrame des salariés prétraité : une ligne par salarié, avec sa fourchette de grille, la médiane
du marché et ses ratios. C'est le DataFrame sur lequel l'analyse va travailler.
S'il trouve aussi un fichier des diplômes (diplomes.xlsx, rangé à côté de celui des salariés), il
ajoute à chaque salarié son niveau d'études le plus élevé et la catégorie de ce diplôme. Ce fichier
est facultatif : sans lui, tout se passe comme avant.

C'est la première étape : il n'a besoin d'aucun autre fichier du projet. Le DataFrame qu'il rend est
l'entrée d'anomaly_cohortes.py, dont la sortie est à son tour l'entrée d'anomaly_regles.py, puis
d'anomaly_signal_iforest.py, puis d'anomaly_signal_regression.py.

Utilisation :
- depuis Python :
      from anomaly_pretraitement import preparer_employes
      df = preparer_employes("input/employes.xlsx", "input/bands.xlsx", "input/market.xlsx")
  (les diplômes sont cherchés tout seuls dans input/diplomes.xlsx ; un autre fichier se donne en
  quatrième : preparer_employes(..., "autre_dossier/diplomes.xlsx"))
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

# Les colonnes du fichier des diplômes, et les autres noms acceptés pour chacune. Pourquoi plusieurs
# noms : le notebook des diplômes les appelle matricule, niveau_max et categorie_diplome_max dans ses
# calculs, puis Niveau_Etude_Max et Cat_Ecole_Max à l'export. Le fichier passe quel que soit le nom
# utilisé, sans tenir compte des majuscules, des espaces ni des « _ ».
NOMS_DIPLOMES = {
    "Matricule": ["matricule"],
    "Niveau_Etude_Max": ["niveauetudemax", "niveaumax"],
    "Cat_Ecole_Max": ["catecolemax", "categoriediplomemax"],
}
# Les colonnes que ce fichier ajoute au tableau des salariés.
COLONNES_AJOUTEES = ["Niveau_Etude_Max", "Cat_Ecole_Max", "Rang_Etude_Max", "Tranche_Etude"]


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


def cle_matricule(matricules: pd.Series) -> pd.Series:
    """Le matricule tel qu'on le compare d'un fichier à l'autre. Le matricule affiché, lui, ne change pas.
    - En texte, sans espace autour, en majuscules : « mat00001 » ou « Mat00001 » suivi d'une espace,
      tapés à la main dans un des deux fichiers, retrouvent « Mat00001 ».
    - Sans « .0 » à la fin : quand une colonne de matricules en chiffres a une seule case vide, Excel la
      donne en nombres à virgule, et 1001 devient « 1001.0 ».
    - Sans zéros au début d'un matricule fait seulement de chiffres : Excel lit « 00123 » comme le
      nombre 123 dans un fichier, et le garde en texte dans l'autre s'il y a aussi des lettres.
    - Un matricule vide reste vide : il ne retrouve personne.
    """
    cle = matricules.astype("string").str.strip().str.upper()
    cle = cle.str.replace(r"\.0$", "", regex=True).str.replace(r"^0+(?=\d+$)", "", regex=True)
    return cle.replace("", pd.NA)


def lire_diplomes(chemin) -> pd.DataFrame:
    """Lit le fichier des diplômes et rend ses trois colonnes sous leurs noms habituels.
    Pourquoi la feuille Vue_salarie : c'est la feuille « une ligne par salarié » du classeur que sort le
    notebook des diplômes (BDD_Diplomes_FINAL) ; on peut donc le déposer tel quel. Sinon, la première
    feuille est lue, comme pour les autres fichiers d'entrée.
    """
    nom = Path(chemin).name
    try:
        classeur = pd.ExcelFile(chemin)
        feuille = "Vue_salarie" if "Vue_salarie" in classeur.sheet_names else 0
        dipl = classeur.parse(feuille)
    except Exception as erreur:
        # Pourquoi un message à nous : celui de Python, en anglais, ne dit ni quel fichier ni quoi faire.
        raise ValueError(f"Impossible de lire {nom} ({erreur}). S'il est ouvert dans Excel, le fermer ; "
                         "sinon, le réenregistrer en classeur Excel (.xlsx), ou le retirer du dossier "
                         "input/ pour lancer l'analyse sans les diplômes.") from erreur

    # Chaque colonne est reconnue sous un de ses noms acceptés, puis prend son nom habituel.
    def simple(nom_colonne):
        return "".join(str(nom_colonne).split()).replace("_", "").lower()

    renommage = {}
    for colonne in dipl.columns:
        for nom_habituel, autres in NOMS_DIPLOMES.items():
            if simple(colonne) in autres and nom_habituel not in renommage.values():
                renommage[colonne] = nom_habituel
    dipl = dipl.rename(columns=renommage)
    manquantes = [c for c in NOMS_DIPLOMES if c not in dipl.columns]
    if manquantes:
        raise ValueError(f"Il manque la colonne {', '.join(manquantes)} dans {nom} "
                         f"(colonnes trouvées : {', '.join(map(str, dipl.columns))}).")
    return dipl[list(NOMS_DIPLOMES)]


def ajouter_diplomes(df: pd.DataFrame, chemin_diplomes) -> pd.DataFrame:
    """Ajoute à chaque salarié quatre colonnes tirées du fichier des diplômes :
    - Niveau_Etude_Max : son niveau d'études le plus élevé, tel qu'écrit dans le fichier (« BAC+5 ») ;
    - Cat_Ecole_Max : la catégorie de ce diplôme (« DIPLOME D'INGENIEUR »...), telle qu'écrite ;
    - Rang_Etude_Max : le rang de ce niveau, de 0 à 7 (voir RANG_NIVEAU_ETUDE) ;
    - Tranche_Etude : sa tranche, « BAC+2 ou moins », « BAC+3 ou BAC+4 » ou « BAC+5 et plus ».
    Un salarié absent du fichier garde ces cases vides. Sans fichier, elles restent vides pour tout le
    monde (ou gardent ce que employes.xlsx en dit déjà) : les colonnes existent quand même, pour que les
    étapes suivantes les trouvent.
    Ce qu'il a trouvé (lignes lues, salariés retrouvés, doublons) est rangé dans df.attrs, une petite
    fiche que pandas accroche au tableau ; message_diplomes la lit pour l'écrire dans le terminal.
    """
    bilan = {"fichier": False}
    if chemin_diplomes is not None and Path(chemin_diplomes).exists():
        dipl = lire_diplomes(chemin_diplomes)
        dipl["cle"] = cle_matricule(dipl["Matricule"])
        dipl = dipl.dropna(subset=["cle"])
        # Un matricule présent deux fois : on garde le niveau le plus élevé, puisque le fichier est censé
        # donner « le diplôme le plus élevé ». Sans ce tri, la valeur gardée dépendrait de l'ordre des lignes.
        dipl["rang"] = rang_etude(dipl["Niveau_Etude_Max"])
        doublons = int(dipl["cle"].duplicated().sum())
        dipl = dipl.sort_values("rang", ascending=False, na_position="last").drop_duplicates(subset="cle")
        # Le fichier des diplômes fait foi : si employes.xlsx a déjà des colonnes du même nom, elles sont
        # retirées avant la fusion. Sans cela, pandas garderait les deux en les renommant (_x, _y) et la
        # suite ne trouverait plus Niveau_Etude_Max.
        df = df.drop(columns=[c for c in COLONNES_AJOUTEES if c in df.columns])
        # how="left" : on garde tous les salariés, même ceux qui ne sont pas dans le fichier des diplômes.
        # indicator : marque chaque salarié retrouvé, pour le compter (même si son niveau est vide).
        df = (df.assign(cle=cle_matricule(df["Matricule"]))
                .merge(dipl[["cle", "Niveau_Etude_Max", "Cat_Ecole_Max"]], on="cle", how="left",
                       indicator=True))
        retrouves = int(df["_merge"].eq("both").sum())
        df = df.drop(columns=["cle", "_merge"])
        bilan = {"fichier": True, "lignes": len(dipl) + doublons, "doublons": doublons, "retrouves": retrouves}
    else:
        for colonne in ["Niveau_Etude_Max", "Cat_Ecole_Max"]:
            if colonne not in df.columns:
                df[colonne] = np.nan

    df["Rang_Etude_Max"] = rang_etude(df["Niveau_Etude_Max"])
    df["Tranche_Etude"] = tranche_etude(df["Rang_Etude_Max"])
    # Les niveaux écrits qui n'ont pas de rang, hors « NON DETERMINE » : une faute de frappe se voit ainsi
    # dans le terminal au lieu de passer en « niveau inconnu » sans rien dire.
    sans_rang = df.loc[df["Niveau_Etude_Max"].notna() & df["Rang_Etude_Max"].isna(), "Niveau_Etude_Max"]
    bilan["non_reconnus"] = sorted(set(sans_rang.astype(str)) - {"NON DETERMINE"})
    df.attrs["diplomes"] = bilan
    return df


def message_diplomes(df: pd.DataFrame) -> str:
    """Une phrase, pour le terminal, qui dit si les diplômes ont été retrouvés. Pourquoi : si les
    matricules ne sont pas écrits de la même façon dans les deux fichiers, aucun salarié ne retrouve son
    diplôme, et rien ne le montrerait dans les résultats, à part des colonnes vides.
    """
    def nombre(n):
        return f"{n:,}".replace(",", " ")

    bilan = df.attrs.get("diplomes", {"fichier": False})
    if not bilan["fichier"]:
        return "Pas de fichier des diplômes (diplomes.xlsx) : les colonnes du diplôme restent vides."
    if bilan["lignes"] == 0:
        return "Le fichier des diplômes n'a aucune ligne avec un matricule : les colonnes du diplôme restent vides."
    if bilan["retrouves"] == 0:
        return ("Attention : aucun matricule de diplomes.xlsx ne correspond à ceux de employes.xlsx. "
                "Vérifier qu'ils sont écrits de la même façon dans les deux fichiers. "
                "En attendant, les colonnes du diplôme restent vides.")
    # « salarié » ou « salariés » selon le nombre : « 1 salarié », mais « 2 salariés ».
    salaries = "salarié" if bilan["retrouves"] == 1 else "salariés"
    texte = (f"Diplômes retrouvés pour {nombre(bilan['retrouves'])} {salaries} sur {nombre(len(df))}, "
             f"dont {nombre(int(df['Rang_Etude_Max'].notna().sum()))} avec un niveau d'études connu.")
    if bilan["doublons"]:
        texte += (f" {nombre(bilan['doublons'])} matricule(s) en double dans le fichier : le niveau le plus "
                  "élevé est gardé.")
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


def preparer_employes(chemin_employes, chemin_bands, chemin_market, chemin_diplomes=None) -> pd.DataFrame:
    """Lit les fichiers d'entrée et rend le DataFrame des salariés prétraité.

    chemin_diplomes : le fichier des diplômes. Sans précision, c'est diplomes.xlsx, dans le même dossier
    que le fichier des salariés (input/diplomes.xlsx). Pourquoi le chercher là tout seul : chaque étape
    du dossier src/ se lance seule et refait le prétraitement ; elle trouve ainsi les diplômes sans
    qu'on ait à le lui dire, et donne les mêmes résultats que le programme principal.

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
       - MarketRatio = salaire / médiane du marché : 1 veut dire « payé comme le marché ».
    6. Ajouter le niveau d'études de chaque salarié, s'il y a un fichier des diplômes (ajouter_diplomes).
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

    # 6. Niveau d'études.
    if chemin_diplomes is None:
        chemin_diplomes = Path(chemin_employes).with_name("diplomes.xlsx")
    df = ajouter_diplomes(df, chemin_diplomes)

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
    df.to_excel(sortie, index=False)
    print(f"\n{len(df)} salariés - DataFrame enregistré dans : {sortie}")
