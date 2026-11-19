"""
Generation des 3 tables sources : bands, employes, market_shifted. DEUXIEME VERSION (12/11/2026).
La premiere version, generate_sources.py, est gardee telle quelle : elle suit la spec
"Specification de la generation de donnees" (v finale, sept. 2026) et tire le salaire au hasard
dans la grille. Celle-ci part du meme code, mais les salaries fictifs ressemblent a ceux d'une
banque marocaine : le salaire suit le profil (voir « CE QUI FAIT LE SALAIRE » plus bas).
Les deux ecrivent les trois memes fichiers dans input/ : le dernier lance remplace l'autre.
      python src/generate_sources_realiste.py    -> salaires qui suivent le profil
      python src/generate_sources.py             -> salaires au hasard dans la grille (spec)
Attention : ces regles sont des hypotheses de bon sens, pas des mesures. Ce qu'un modele retrouve
sur ces donnees, c'est ce qu'on y a mis ; cela ne dit rien des vraies donnees.

Tous les parametres ajustables sont regroupes dans la section PARAMETRES.
Pour passer de l'echantillon a la volumetrie cible : N_EMPLOYES = 10000.

Vue d'ensemble de ce que fait le script :
  1. BANDS    : pour chaque famille de metiers et chaque niveau (1 a 7), calcule
                une grille salariale interne (Min / Mid / Max).
  2. MARKET   : pour les memes couples famille x niveau, calcule les references
                du marche (P25 / Median / P75), derivees de la grille interne.
  3. EMPLOYES : genere des employes fictifs (famille, niveau, poste, salaire,
                age, anciennete, sexe, etc.) dont le salaire tombe dans la
                bande, plus ou moins haut selon le profil : anciennete, performance,
                diplome, marche... Quelques-uns (3 %) sont places au-dessus du Max de
                leur bande : les « outliers positifs », que la detection range a part.
                Les postes sont de simples numeros (JT0001, JT0002...)
                et chacun porte un Hot_job de 0 a 2. Chaque employe recoit
                un diplome (niveau d'etudes et categorie d'ecole), une
                performance N-1 (5 libelles, de « Tres en dessous » a « Tres
                au-dela ») et un positionnement 9-Box (6 categories, de
                « Hauts Potentiels » a « Decisions requises »).
  4. EXPORT   : ecrit les 3 tables en Excel (.xlsx) dans le dossier input/ et affiche
                quelques controles de coherence.
"""

# Counter compte les occurrences d'une liste, ex. Counter([1, 1, 2]) -> {1: 2, 2: 1}.
from collections import Counter
# Path permet de manipuler les chemins de fichiers de facon portable (Windows / Linux).
from pathlib import Path

# numpy : calcul numerique et tirages aleatoires (loi normale, uniforme, choix...).
import numpy as np
# pandas : manipulation de tableaux de donnees (DataFrame) et export Excel.
import pandas as pd

# ----------------------------------------------------------------------------
# PARAMETRES
# ----------------------------------------------------------------------------
# Graine du generateur aleatoire : avec la meme graine, le script produit
# exactement les memes donnees a chaque execution (reproductibilite).
SEED = 20260909
# Nombre total d'employes a generer.
N_EMPLOYES = 10000            # <-- mettre 10000 pour la volumetrie cible
# Liste des niveaux [1, 2, 3, 4, 5, 6, 7] ; range(1, 8) s'arrete avant 8.
NIVEAUX = list(range(1, 8))  # 1 = plus eleve, 7 = plus bas
# Pays unique de toutes les lignes generees.
PAYS = "Maroc"
# Devise des salaires (dirham marocain).
DEVISE = "MAD"
# Date d'effet de la paie, recopiee telle quelle sur chaque employe.
DATE_EFFET = "01/08/2025"

# Liste des 13 familles de metiers (Job_Family) de l'entreprise.
FAMILLES = [
    "AUDIT", "COMMUNICATION", "CONFORMITE", "DATA", "FINANCE",
    "GESTION DES RISQUES", "IT", "RETAIL BANKING", "RH", "STRATEGIE",
    "TRANSFORMATION", "JURIDIQUE", "TRANSVERSE",
]

# Ancrage : valeur du Mid au niveau 7.
# C'est le point de depart de la grille : tous les autres niveaux sont
# calcules a partir de cette valeur en multipliant par COEF.
ANCRAGE_G7 = {
    "AUDIT": 126.0,
    "IT": 200.0,
    "DATA": 200.0,

    "CONFORMITE": 126.0,
    "GESTION DES RISQUES": 126.0,
    "JURIDIQUE": 126.0,
    "FINANCE": 126.0,
    "RH": 126.0,
    "COMMUNICATION": 126.0,
    "RETAIL BANKING": 126.0,
    "STRATEGIE": 126.0,
    "TRANSFORMATION": 126.0,
    "TRANSVERSE": 126.0,
}
# Familles dont l'ancrage a ete fourni par la spec (les autres sont supposes).
# Information documentaire : cette variable n'est pas utilisee dans le calcul.
ANCRAGE_FOURNI = {"AUDIT", "IT"}

# Coefficient de progression d'un niveau a l'autre, fixe par l'ancrage du niveau 7 :
# les familles ancrees a 126 prennent 1.30, celles ancrees a 200 (IT, DATA) 1.25.
# Exemple : avec 1.30, le Mid du niveau 6 = Mid du niveau 7 x 1.30,
# le Mid du niveau 5 = Mid du niveau 6 x 1.30, etc.
COEF_PAR_ANCRAGE = {126.0: 1.30, 200.0: 1.25}
# Coefficient de chaque famille, lu a partir de son ancrage : on ne peut pas
# changer l'ancrage d'une famille sans que son coefficient suive.
COEF = {f: COEF_PAR_ANCRAGE[ANCRAGE_G7[f]] for f in FAMILLES}

# Bornes de la bande interne : Min = Mid x 0.67, Max = Mid x 1.33.
MIN_RATIO, MAX_RATIO = 0.67, 1.33      # Mid -/+ 33%
# Bornes du marche : P25 = Median x 0.66, P75 = Median x 1.33.
P25_RATIO, P75_RATIO = 0.66, 1.33      # market_shifted

# Decalage marche vs interne : Median du marche = Mid x decalage. 1.00 = le marche paie comme la
# grille ; 1.12 = le marche paie 12 % de plus que la grille.
# Pourquoi des valeurs differentes : dans une banque, les metiers que tout le monde s'arrache (IT,
# data, risques, conformite) sont mieux payes ailleurs que ce que prevoit la grille ; le reseau
# d'agences et les fonctions support le sont un peu moins.
# Pour revenir a la spec litterale (Median == Mid partout) : mettre 1.00 a toutes les familles
# et MARKET_ECART_NIVEAU a 0.
MARKET_SHIFT = {
    "DATA": 1.15, "IT": 1.12,
    "GESTION DES RISQUES": 1.06, "CONFORMITE": 1.05, "STRATEGIE": 1.04,
    "AUDIT": 1.03, "TRANSFORMATION": 1.03, "FINANCE": 1.02,
    "JURIDIQUE": 1.00,
    "RH": 0.98, "TRANSVERSE": 0.98, "COMMUNICATION": 0.97, "RETAIL BANKING": 0.97,
}
# En plus du decalage de la famille, chaque couple famille x niveau s'ecarte un peu, au hasard :
# 0.03 = entre -3 % et +3 %. Pourquoi : une enquete de marche ne tombe jamais pile sur le meme
# ecart a tous les niveaux d'un metier.
MARKET_ECART_NIVEAU = 0.03

# Mapping famille -> pole
# Chaque famille est rattachee a un pole (Entite_N1) numerote de 1 a 5.
POLE_MAP = {
    "AUDIT": 1, "CONFORMITE": 1, "GESTION DES RISQUES": 1, "JURIDIQUE": 1,
    "RH": 2, "COMMUNICATION": 2, "STRATEGIE": 2,
    "RETAIL BANKING": 3,
    "FINANCE": 4, "IT": 4, "DATA": 4,
    "TRANSFORMATION": 5,
    "TRANSVERSE": None,  # aleatoire
}
# Nombre d'entites N2 (sous-directions) dans chaque pole.
# Ex. le pole 1 contient les entites P1-E01 a P1-E15.
N_ENTITES_N2 = {1: 15, 2: 7, 3: 20, 4: 13, 5: 17}

# Effectifs cibles sur 10 000 (repartition proportionnelle si N_EMPLOYES < 10000)
# La somme de ces valeurs fait 10 000 ; ce sont des poids relatifs.
EFFECTIFS_10K = {
    "RETAIL BANKING": 5000, "IT": 1200, "FINANCE": 900,
    "GESTION DES RISQUES": 700, "RH": 500, "CONFORMITE": 400, "AUDIT": 300,
    "TRANSFORMATION": 250, "DATA": 200, "JURIDIQUE": 200,
    "COMMUNICATION": 150, "STRATEGIE": 100, "TRANSVERSE": 100,
}
# Part des effectifs RETAIL BANKING partageant un meme poste (2000/5000).
# Ce poste commun prend le premier numero (JT0001) ; mettre 0 pour le supprimer.
RETAIL_TITRE_UNIQUE_PART = 0.40

# Nombre de postes (Job_Title) differents. Un poste n'a pas de libelle :
# c'est un numero incremente, JT0001, JT0002, ..., JT2000.
N_POSTES = 2000
# Hot_job : tension du metier sur le marche, de 0 (faible) a 2 (forte).
# Part des employes visee pour chaque valeur (total = 100%) : un tiers chacune.
# Tous les employes d'un meme poste ont le meme Hot_job.
HOT_JOB_PARTS = {0: 1 / 3, 1: 1 / 3, 2: 1 / 3}

# Distribution des niveaux : identique pour toutes les familles (pyramide)
# Probabilite d'avoir le niveau 1, 2, ..., 7 (peu de directeurs, beaucoup de juniors).
POIDS_NIVEAU = np.array([0.04, 0.07, 0.11, 0.17, 0.22, 0.22, 0.17])

# Age et anciennete. On ne tire plus l'age au hasard : on le reconstruit comme dans la vraie vie,
#     age = age a la fin des etudes + annees travaillees ailleurs avant d'entrer + anciennete.
# Pourquoi : dans une banque on reste longtemps, donc l'age et l'anciennete vont ensemble, et les
# hauts niveaux sont tenus par des salaries plus anciens. Avec deux tirages independants, un
# directeur de 24 ans etait aussi probable qu'un guichetier de 24 ans.
# Age a la fin des etudes, selon le niveau d'etudes.
AGE_FIN_ETUDES = {
    "SECONDAIRE": 20, "BAC": 20, "BAC+1": 21, "BAC+2": 21, "BAC+3": 22, "BAC+4": 23, "BAC+5": 24,
    "BAC+6": 25, "BAC+7": 27, "EXPERTISE COMPTABLE": 27, "NON DETERMINE": 22,
}
# Annees travaillees ailleurs avant d'entrer, en moyenne, selon le niveau du poste (1 = le plus
# haut). Pourquoi plus pour les hauts niveaux : on y recrute plus souvent des profils experimentes.
EXPERIENCE_AVANT_MOYENNE = {7: 1.5, 6: 2.5, 5: 3.5, 4: 4.5, 3: 6.0, 2: 7.5, 1: 9.0}
# Anciennete moyenne (en annees) selon le niveau du poste : on monte de niveau avec les annees.
ANC_MOYENNE = {7: 4, 6: 7, 5: 9, 4: 12, 3: 15, 2: 18, 1: 21}
# Dispersion de l'anciennete autour de cette moyenne (forme de la loi gamma) : plus le nombre est
# petit, plus on trouve a la fois des tout nouveaux et des tres anciens dans un meme niveau.
ANC_FORME = 1.6
# Bornes : anciennete de 0 a 38 ans, depart a la retraite a 60 ans.
ANC_MAX, AGE_MAX = 38, 60
# Contrainte de realisme, verifiee a la fin : on ne peut pas etre entre avant 18 ans
# (Age - Anciennete doit etre >= 18).
ECART_AGE_ANC_MIN = 18
# Probabilite qu'un employe soit une femme (46%).
PART_FEMMES = 0.46
# Note de competence : loi normale de moyenne 3.35 et ecart-type 0.60 (sur 5).
COMP_MU, COMP_SD = 3.35, 0.60

# Diplome : (Niveau_Etude_Max, Cat_Ecole_Max) et nombre de salaries sur 10 000.
# Pourquoi ces nombres : ce sont ceux du fichier des diplomes deja utilise pour les tests
# (input/diplomes.xlsx), pour que le fichier regenere garde les memes proportions.
# Les nombres par diplome sont respectes exactement, mais le diplome n'est plus donne au hasard :
# les hauts niveaux et certains metiers ont plus souvent un diplome eleve (voir LIEN_DIPLOME_POSTE).
# « NON DETERMINE » n'a pas de categorie d'ecole (case vide, comme dans le vrai fichier) ; il
# tombe sur des salaries pris au hasard.
PARTS_DIPLOME = {
    ("SECONDAIRE", "AUTRES"): 47,
    ("BAC", "AUTRES"): 203,
    ("BAC+2", "AUTRES"): 1266,
    ("BAC+2", "DIPLOME DE COMMERCE"): 2,
    ("BAC+2", "DIPLOME UNIVERSITAIRE"): 334,
    ("BAC+3", "AUTRES"): 16,
    ("BAC+3", "DIPLOME D'INGENIEUR"): 34,
    ("BAC+3", "DIPLOME DE COMMERCE"): 131,
    ("BAC+3", "DIPLOME UNIVERSITAIRE"): 2365,
    ("BAC+4", "AUTRES"): 171,
    ("BAC+4", "DIPLOME D'INGENIEUR"): 17,
    ("BAC+4", "DIPLOME DE COMMERCE"): 409,
    ("BAC+4", "DIPLOME UNIVERSITAIRE"): 263,
    ("BAC+5", "DIPLOME D'INGENIEUR"): 775,
    ("BAC+5", "DIPLOME DE COMMERCE"): 2242,
    ("BAC+5", "DIPLOME UNIVERSITAIRE"): 1408,
    ("BAC+6", "DIPLOME DE COMMERCE"): 1,
    ("BAC+6", "DIPLOME UNIVERSITAIRE"): 2,
    ("BAC+7", "DIPLOME D'INGENIEUR"): 2,
    ("BAC+7", "DIPLOME DE COMMERCE"): 2,
    ("BAC+7", "DIPLOME UNIVERSITAIRE"): 21,
    ("EXPERTISE COMPTABLE", "DIPLOME DE COMMERCE"): 2,
    ("EXPERTISE COMPTABLE", "DIPLOME UNIVERSITAIRE"): 1,
    ("NON DETERMINE", None): 286,
}

# Rang de chaque niveau d'etudes, du plus bas au plus haut (le meme que dans la detection).
RANG_ETUDE = {"SECONDAIRE": 0, "BAC": 1, "BAC+1": 2, "BAC+2": 3, "BAC+3": 4, "BAC+4": 5, "BAC+5": 6,
              "BAC+6": 6, "BAC+7": 7, "EXPERTISE COMPTABLE": 7}
# Lien entre le poste et le diplome, de 0 (aucun : diplome au hasard) a 1 (le plus haut poste a
# toujours le plus haut diplome). Pourquoi 0.6 : un cadre superieur a le plus souvent un BAC+5,
# mais on trouve aussi des BAC+2 montes par l'anciennete.
LIEN_DIPLOME_POSTE = 0.6
# Metiers ou l'on recrute plus diplome que la moyenne (ecart ajoute au score du poste ; un niveau
# de poste en plus compte pour 0.5) : l'informatique et la data recrutent surtout a BAC+5, le
# reseau d'agences beaucoup a BAC+2 / BAC+3.
BONUS_DIPLOME_FAMILLE = {"DATA": 1.5, "IT": 1.2, "STRATEGIE": 1.0, "GESTION DES RISQUES": 0.8,
                         "AUDIT": 0.6, "FINANCE": 0.5, "JURIDIQUE": 0.5, "CONFORMITE": 0.4,
                         "TRANSFORMATION": 0.4, "RETAIL BANKING": -0.4}
# Metiers ou l'on trouve surtout des ingenieurs, et metiers ou l'on trouve surtout des diplomes
# d'ecoles de commerce : a niveau d'etudes egal, ces categories y vont en priorite.
FAMILLES_INGENIEUR = {"IT", "DATA", "GESTION DES RISQUES", "TRANSFORMATION"}
FAMILLES_COMMERCE = {"FINANCE", "AUDIT", "STRATEGIE", "RETAIL BANKING", "COMMUNICATION", "RH"}

# Performance N-1 : les 5 libelles de la matrice Performance x Competence, du plus bas au
# plus haut, avec la part des salaries pour chacun (total = 100 %).
PARTS_PERFORMANCE = {
    "Très en dessous": 0.05,
    "Proche de l'objectif": 0.15,
    "A l'objectif": 0.45,
    "Supérieur à l'objectif": 0.25,
    "Très au-delà": 0.10,
}
# Lien entre performance et competence, de 0 (aucun) a 1 (la performance suit exactement
# la competence). Pourquoi 0.5 : un salarie bien note en competence a plus souvent une bonne
# performance, sans que ce soit automatique, comme dans la realite.
LIEN_PERF_COMP = 0.5

# Positionnement 9-Box : une des six categories du tableau de bord RH, donnee par la formule
# Excel des RH a partir de la performance N-1 et de la competence (voir positionnement_9box).
# Pourquoi des seuils pour la competence : la formule lit la competence en libelles
# (Exceptionnel... Tres insuffisant), alors que le fichier la donne en note. Ces seuils ne
# servent qu'a fabriquer des donnees fictives coherentes : la detection et la page LISENT
# le positionnement dans le fichier, elles ne le recalculent jamais.
# (note minimale, libelle), de la plus haute a la plus basse.
SEUILS_COMPETENCE = [(4.25, "Exceptionnel"), (3.75, "Supérieur aux attentes"),
                     (2.75, "Conforme aux attentes"), (2.0, "Proche des attentes"),
                     (-np.inf, "Très insuffisant")]

# ----------------------------------------------------------------------------
# CE QUI FAIT LE SALAIRE
# ----------------------------------------------------------------------------
# Le salaire = Mid de la grille x Compa-Ratio. Le Compa-Ratio (1.00 = pile au milieu de la grille)
# est fabrique en ajoutant les effets ci-dessous, tous en « % de salaire en plus » (0.03 = +3 %),
# puis une part de hasard. Ce sont des hypotheses de bon sens pour une banque marocaine, pas des
# mesures : pour en retirer un, mettre son effet a 0.
# Compa-Ratio moyen de l'entreprise : un peu sous le milieu de la grille, comme souvent.
CR_MOYEN = 0.97

# 1. L'anciennete DANS LE NIVEAU. C'est le premier moteur : apres une promotion, on entre en bas de
#    la nouvelle grille, puis les augmentations annuelles et la prime d'anciennete font monter.
#    L'effet monte vite les premieres annees, puis plafonne : +EFFET_ANC_MAX au bout de tres
#    longtemps, les deux tiers de ce maximum au bout de ANC_VITESSE annees.
#    Attention : le fichier ne donne PAS l'anciennete dans le niveau, seulement l'anciennete dans
#    l'entreprise. Le temps passe dans le niveau actuel est tire au hasard (ANC_NIVEAU_MOYENNE
#    annees en moyenne), sans depasser l'anciennete dans l'entreprise : un salarie entre il y a
#    3 ans a au plus 3 ans dans son niveau, un salarie entre il y a 20 ans peut avoir ete promu
#    l'an dernier. C'est voulu : comme dans les vraies donnees, une partie de l'explication
#    manque au fichier, et aucun modele ne peut la retrouver.
EFFET_ANC_MAX = 0.24
ANC_VITESSE = 6.0
ANC_NIVEAU_MOYENNE = 7.0
# 2. La performance N-1 : les augmentations au merite.
EFFET_PERFORMANCE = {"Très en dessous": -0.05, "Proche de l'objectif": -0.02, "A l'objectif": 0.0,
                     "Supérieur à l'objectif": 0.025, "Très au-delà": 0.05}
# 3. La competence : par point de note au-dessus de la moyenne.
EFFET_COMPETENCE = 0.02
# 4. Le diplome : par rang d'etudes au-dessus de BAC+3, puis selon la categorie d'ecole (les
#    grandes ecoles negocient un meilleur salaire d'entree, et l'ecart reste).
EFFET_RANG_ETUDE = 0.008
EFFET_ECOLE = {"DIPLOME D'INGENIEUR": 0.03, "DIPLOME DE COMMERCE": 0.015,
               "DIPLOME UNIVERSITAIRE": 0.0, "AUTRES": -0.01}
# 5. L'experience acquise ailleurs avant d'entrer : par annee, jusqu'a un plafond.
EFFET_EXPERIENCE_AVANT, EFFET_EXPERIENCE_AVANT_MAX = 0.004, 0.06
# 6. Le Hot job : par cran de tension du metier (0 a 2).
EFFET_HOT_JOB = 0.025
# 7. Le marche : la part de l'ecart entre le marche et la grille que le salaire rattrape. 0.5 = si
#    le marche paie 12 % de plus que la grille, les salaries du metier sont payes environ 6 % plus
#    haut dans leur grille (on les recrute et on les retient au prix du marche).
PART_MARCHE = 0.5
# 8. L'ecart femmes / hommes a profil egal : -0.02 = une femme est payee 2 % de moins qu'un homme
#    de meme profil. Pourquoi il y en a un : c'est ce qu'on constate dans la plupart des
#    entreprises, et l'analyse des ecarts femmes / hommes a ainsi quelque chose a trouver.
#    Mettre 0 pour des donnees sans ecart.
EFFET_FEMME = -0.02
# 9. Le hasard : tout ce que le fichier ne dit pas (negociation a l'embauche, historique des
#    augmentations, manager...). C'est l'ecart-type de cette part, en % de salaire. Plus il est
#    grand, moins un modele peut expliquer le Compa-Ratio.
BRUIT = 0.055
# 10. Les salaries payes AU-DESSUS du Max de leur grille (les « outliers positifs »). Pourquoi en
#     mettre : dans les vraies donnees il y en a (anciens salaries plafonnes, embauches negociees
#     au-dessus de la grille, experts qu'on veut garder), et la detection les range a part dans
#     la priorite « Outlier positif ». Sans eux, cette categorie reste vide et on ne peut ni la
#     voir dans le tableau de bord, ni essayer leur retrait dans les notebooks de regression.
#     PART_OUTLIERS_POSITIFS : la part des salaries concernes (0.03 = 3 %, soit 300 sur 10 000).
#     Mettre 0 pour revenir a des donnees ou tout le monde est dans sa grille.
#     DEPASSEMENT_MIN, DEPASSEMENT_MAX : de combien le salaire depasse le Max, tire au hasard
#     entre les deux (0.02 et 0.50 = entre 2 % et 50 % au-dessus du Max). Exemple : Max = 300,
#     depassement tire = 0.10 -> salaire = 330.
PART_OUTLIERS_POSITIFS = 0.03
DEPASSEMENT_MIN, DEPASSEMENT_MAX = 0.02, 0.50


# ----------------------------------------------------------------------------
# 1. BANDS
# ----------------------------------------------------------------------------
def mid_par_niveau(famille):
    """Mid(niveau) = Mid(niveau+1) x coef, en remontant du niveau 7 au niveau 1."""
    # Recupere le coefficient de progression de la famille (ex. 1.30).
    coef = COEF[famille]
    # Initialise le dictionnaire {niveau: mid} avec la valeur d'ancrage du niveau 7.
    mids = {7: ANCRAGE_G7[famille]}
    # Parcourt les niveaux 6, 5, 4, 3, 2, 1 (range(6, 0, -1) descend jusqu'a 1).
    for g in range(6, 0, -1):
        # Le Mid du niveau g = Mid du niveau juste en dessous (g + 1) x coef.
        mids[g] = mids[g + 1] * coef
    # Renvoie par ex. {7: 126, 6: 163.8, 5: 212.94, ...}.
    return mids


# repartir : partage un nombre total (ex. les employes) entre plusieurs groupes
# (ex. les familles) proportionnellement a leurs poids, en garantissant :
#   - que chaque groupe recoit un nombre ENTIER (pas 3,5 employes) ;
#   - que la somme fait EXACTEMENT le total demande (aucun employe perdu ou en trop).
# Exemple : 7 employes, poids A=5000, B=3000, C=2000
#   parts exactes : A=3.5, B=2.1, C=1.4 -> arrondi vers le bas : 3, 2, 1 (total 6)
#   il manque 1 -> il va a A (plus grosse decimale perdue) -> A=4, B=2, C=1 (total 7).
# Avec N_EMPLOYES = 10000 les parts tombent juste ; utile si on change N_EMPLOYES.
def repartir(n_total, poids_dict):
    """Repartition entiere proportionnelle (methode des plus forts restes)."""
    # Somme de tous les poids (ici 10 000).
    tot = sum(poids_dict.values())
    # Part exacte (decimale) de chaque cle : poids / total x nombre a repartir.
    exact = {k: v / tot * n_total for k, v in poids_dict.items()}
    # Partie entiere de chaque part (arrondi vers le bas).
    base = {k: int(np.floor(v)) for k, v in exact.items()}
    # Nombre d'unites perdues a cause des arrondis vers le bas.
    reste = n_total - sum(base.values())
    # Trie les cles de la plus grande partie decimale a la plus petite.
    ordre = sorted(exact, key=lambda k: exact[k] - base[k], reverse=True)
    # Donne +1 aux cles ayant les plus grosses decimales, jusqu'a epuiser le reste.
    for k in ordre[:reste]:
        base[k] += 1
    # Renvoie des effectifs entiers dont la somme vaut exactement n_total.
    return base


# attribuer_postes : cree les postes (Job_Title) et y range les employes.
# Un poste est un simple numero. Il appartient a une seule famille et un seul
# niveau, sauf le poste commun RETAIL BANKING qui melange les niveaux.
# Les N_POSTES postes sont partages entre les couples famille x niveau selon
# leur effectif : une cellule de 400 employes a plus de postes qu'une de 10.
# Chaque poste recoit au moins un employe, pour retrouver exactement
# N_POSTES intitules differents dans employes.xlsx.
def attribuer_postes(fam_emp, niveau_emp, commun_emp, rng):
    """Renvoie le numero de poste (1, 2, ...) de chaque employe."""
    # Numero de poste de chaque employe, rempli au fur et a mesure.
    poste_emp = [0] * len(fam_emp)
    # Dernier numero attribue (0 = aucun pour l'instant).
    numero = 0

    # Poste commun RETAIL BANKING : il prend le premier numero (JT0001).
    idx_commun = [k for k, commun in enumerate(commun_emp) if commun]
    if idx_commun:
        numero = 1
        for k in idx_commun:
            poste_emp[k] = numero

    # Regroupe les autres employes par cellule famille x niveau :
    # {("IT", 5): [positions des employes IT de niveau 5], ...}.
    cellules = {}
    for k, (fam, g, commun) in enumerate(zip(fam_emp, niveau_emp, commun_emp)):
        if not commun:
            # setdefault cree la liste vide la premiere fois que la cellule apparait.
            cellules.setdefault((fam, g), []).append(k)

    # Nombre de postes restant a creer, sans depasser le nombre d'employes
    # (sinon certains postes resteraient vides).
    n_postes = min(N_POSTES - numero, sum(len(idx) for idx in cellules.values()))
    # Chaque cellule recoit d'office 1 poste ; les postes restants sont repartis
    # selon l'effectif de la cellule moins 1 (l'employe deja couvert par ce poste).
    # Une cellule d'un seul employe garde ainsi exactement 1 poste.
    supplement = repartir(n_postes - len(cellules),
                          {c: len(idx) - 1 for c, idx in cellules.items()})

    # Parcourt les cellules dans l'ordre (famille, puis niveau) pour numeroter les postes.
    for cellule in sorted(cellules):
        # Nombre de postes de la cellule, numerotes a la suite des precedents.
        n_cell = 1 + supplement[cellule]
        numeros = list(range(numero + 1, numero + n_cell + 1))
        numero += n_cell
        # Melange les employes de la cellule.
        idx = rng.permutation(cellules[cellule])
        # Les n_cell premiers occupent chacun un poste different : aucun poste vide.
        for k, num in zip(idx[:n_cell], numeros):
            poste_emp[k] = num
        # Les suivants sont repartis au hasard entre ces memes postes.
        for k in idx[n_cell:]:
            poste_emp[k] = int(rng.choice(numeros))
    return poste_emp


def positionnement_9box(performance, note):
    """La categorie 9-Box d'un salarie, avec la formule Excel des RH (09/11/2026). La note de
    competence est d'abord ecrite en libelle avec SEUILS_COMPETENCE."""
    competence = next(libelle for seuil, libelle in SEUILS_COMPETENCE if note >= seuil)
    haute_perf = performance in ("Très au-delà", "Supérieur à l'objectif")
    haute_comp = competence in ("Supérieur aux attentes", "Exceptionnel")
    # Les conditions sont testees dans l'ordre de la formule : la premiere qui est vraie l'emporte.
    if haute_perf and competence == "Supérieur aux attentes":
        return "Talents"
    if haute_comp and performance == "Supérieur à l'objectif":
        return "Talents"
    if performance == "Très au-delà" and competence == "Exceptionnel":
        return "Hauts Potentiels"
    if haute_comp and performance == "A l'objectif":
        return "A repositionner"
    if performance == "A l'objectif" and competence == "Conforme aux attentes":
        return "A développer"
    if haute_perf and competence == "Conforme aux attentes":
        return "Performers"
    return "Décisions requises"


# attribuer_hot_job : donne a chaque poste un Hot_job de 0 a 2 ; tous les
# employes du poste heritent de cette valeur. Les parts de HOT_JOB_PARTS sont
# visees sur les EMPLOYES (ce qu'on lit dans employes.xlsx), pas sur les postes :
# le poste commun RETAIL BANKING (2000 employes) pese 2000, pas 1.
# Methode : on prend les postes du plus gros au plus petit, et chacun va dans
# la valeur la moins remplie par rapport a sa cible, a condition d'y tenir.
# Exemple : le poste commun (2000) tient dans chacune des trois valeurs (cible
# 3333) ; il prend la premiere, et les deux autres ont alors plus de place.
# Les autres postes (quelques employes chacun) remplissent ensuite toutes les
# valeurs au meme rythme, jusqu'a un tiers des employes chacune.
def attribuer_hot_job(taille_poste, rng):
    """Renvoie {numero de poste: Hot_job}."""
    # Somme des parts (1.00), pour tolerer des parts qui ne tomberaient pas pile a 100%.
    total = sum(HOT_JOB_PARTS.values())
    # Nombre total d'employes (somme des tailles de postes).
    n_emp = sum(taille_poste.values())
    # Nombre d'employes vise par valeur, ex. 1/3 x 10000 = 3333 pour Hot_job = 2.
    cible = {h: p / total * n_emp for h, p in HOT_JOB_PARTS.items()}
    # Nombre d'employes deja places dans chaque valeur.
    deja = {h: 0 for h in HOT_JOB_PARTS}
    # Postes melanges, puis tries du plus gros au plus petit
    # (le tri garde l'ordre aleatoire entre postes de meme taille).
    postes = list(taille_poste)
    rng.shuffle(postes)
    postes.sort(key=lambda p: taille_poste[p], reverse=True)

    hot_poste = {}
    for p in postes:
        # Nombre d'employes du poste.
        n = taille_poste[p]
        # Place restante dans chaque valeur de Hot_job.
        reste = {h: cible[h] - deja[h] for h in HOT_JOB_PARTS}
        # Valeurs ou le poste tient en entier.
        possibles = [h for h in HOT_JOB_PARTS if reste[h] >= n]
        if possibles:
            # La moins remplie en proportion de sa cible ; a egalite, la plus grande place.
            h = max(possibles, key=lambda h: (reste[h] / cible[h], reste[h]))
        else:
            # Le poste ne tient nulle part en entier : on le met la ou il reste le plus de place.
            h = max(HOT_JOB_PARTS, key=lambda h: reste[h])
        hot_poste[p] = h
        deja[h] += n
    return hot_poste

# attribuer_diplomes : donne a chaque salarie un diplome de PARTS_DIPLOME, en respectant exactement
# le nombre de salaries par diplome, mais sans tirer au hasard : les postes les plus eleves et
# certains metiers recoivent les diplomes les plus eleves.
# Methode, la meme que pour la performance : chaque salarie recoit un score (son poste + une part
# de hasard), on range les salaries par score, on range les diplomes du plus bas au plus haut, et
# on les distribue dans cet ordre.
def attribuer_diplomes(employes, rng):
    """Renvoie deux listes, dans l'ordre des lignes : le niveau d'etudes et la categorie d'ecole."""
    n = len(employes)
    famille = employes["Job_Family"]
    diplomes = [d for d, k in repartir(n, PARTS_DIPLOME).items() for _ in range(k)]
    # Les « NON DETERMINE » tombent sur des salaries pris au hasard.
    connus = [d for d in diplomes if d[0] in RANG_ETUDE]
    idx_connus = rng.permutation(n)[:len(connus)]
    etude = np.full(n, "NON DETERMINE", dtype=object)
    categorie = np.full(n, None, dtype=object)

    # Score du poste : 0.5 par niveau au-dessus du niveau 7, plus le bonus du metier ; ramene a
    # une moyenne de 0 et un ecart-type de 1 pour pouvoir le melanger au hasard.
    poste = 0.5 * (7 - employes["Niveau"].to_numpy()) + famille.map(BONUS_DIPLOME_FAMILLE).fillna(0).to_numpy()
    poste = (poste - poste.mean()) / poste.std()
    score = LIEN_DIPLOME_POSTE * poste + np.sqrt(1 - LIEN_DIPLOME_POSTE ** 2) * rng.normal(size=n)
    # Les salaries du plus petit score au plus grand, les niveaux d'etudes du plus bas au plus haut.
    idx_tries = idx_connus[np.argsort(score[idx_connus], kind="stable")]
    connus.sort(key=lambda d: RANG_ETUDE[d[0]])
    etude[idx_tries] = [d[0] for d in connus]

    # La categorie d'ecole, niveau d'etudes par niveau d'etudes : les diplomes d'ingenieur vont
    # d'abord aux metiers d'ingenieurs, puis ceux de commerce aux metiers de commerce, et le reste
    # (universite, autres) est distribue au hasard.
    hasard = rng.random(n)
    for niveau_etude in dict.fromkeys(d[0] for d in connus):
        categories = [d[1] for d in connus if d[0] == niveau_etude]
        restants = [int(k) for k in idx_tries if etude[k] == niveau_etude]
        for cat, familles in [("DIPLOME D'INGENIEUR", FAMILLES_INGENIEUR), ("DIPLOME DE COMMERCE", FAMILLES_COMMERCE)]:
            k_cat = categories.count(cat)
            # Priorite aux metiers de la categorie, avec une part de hasard : tout ingenieur ne
            # travaille pas a l'informatique.
            restants.sort(key=lambda k: (famille.iloc[k] in familles) + hasard[k], reverse=True)
            for k in restants[:k_cat]:
                categorie[k] = cat
            restants = restants[k_cat:]
            categories = [c for c in categories if c != cat]
        for k, cat in zip(rng.permutation(restants), categories):
            categorie[k] = cat
    return list(etude), list(categorie)


# attribuer_age_anciennete : reconstruit l'age comme dans la vraie vie (voir AGE_FIN_ETUDES).
def attribuer_age_anciennete(employes, rng):
    """Renvoie l'age et l'anciennete de chaque salarie (deux tableaux d'entiers)."""
    n = len(employes)
    niveau = employes["Niveau"]
    # Age d'entree = fin des etudes + annees travaillees ailleurs. Ces annees suivent une loi
    # exponentielle : la plupart entrent peu apres leurs etudes, quelques-uns bien plus tard.
    avant = rng.exponential(niveau.map(EXPERIENCE_AVANT_MOYENNE).to_numpy(), size=n)
    age_entree = np.round(employes["Niveau_Etude_Max"].map(AGE_FIN_ETUDES).to_numpy() + avant).astype(int)
    # Anciennete : loi gamma autour de la moyenne du niveau, de 0 a ANC_MAX.
    moyenne = niveau.map(ANC_MOYENNE).to_numpy()
    anciennete = np.round(rng.gamma(ANC_FORME, moyenne / ANC_FORME, size=n)).clip(0, ANC_MAX).astype(int)
    # Personne ne depasse l'age de la retraite : on entre au plus tard 1 an avant, et une
    # anciennete trop longue pour l'age d'entree est raccourcie.
    age_entree = np.minimum(age_entree, AGE_MAX - 1)
    anciennete = np.minimum(anciennete, AGE_MAX - age_entree)
    return age_entree + anciennete, anciennete


# calculer_salaires : le salaire de chaque salarie, d'apres son profil (voir « CE QUI FAIT LE
# SALAIRE » dans les parametres).
def calculer_salaires(employes, bands, market, rng):
    """Renvoie le salaire fixe annuel de chaque salarie : entre le Min et le Max de sa grille, sauf
    pour les quelques « outliers positifs » (PART_OUTLIERS_POSITIFS), places au-dessus du Max."""
    n = len(employes)
    cles = ["Job_Family", "Niveau"]
    e = (employes.merge(bands[cles + ["Min", "Mid", "Max"]], on=cles, how="left")
         .merge(market[cles + ["Median"]], on=cles, how="left"))
    # L'anciennete dans le niveau actuel, que le fichier ne donnera pas : un tirage autour de
    # ANC_NIVEAU_MOYENNE annees, ramene a l'anciennete dans l'entreprise s'il la depasse.
    anc_niveau = np.minimum(e["Anciennete"].to_numpy(), rng.gamma(2.0, ANC_NIVEAU_MOYENNE / 2.0, size=n))
    # Annees travaillees ailleurs avant d'entrer.
    avant = (e["Age"] - e["Anciennete"] - e["Niveau_Etude_Max"].map(AGE_FIN_ETUDES)).clip(lower=0).to_numpy()
    # La somme des effets, en logarithme : ajouter 0.03 revient a payer 3 % de plus.
    effets = (
        EFFET_ANC_MAX * (1 - np.exp(-anc_niveau / ANC_VITESSE))
        + e["Performance_N1"].map(EFFET_PERFORMANCE).to_numpy()
        + EFFET_COMPETENCE * (e["Competence_N1"].to_numpy() - COMP_MU)
        # Un niveau d'etudes inconnu compte comme BAC+3 (rang 4), une categorie inconnue pour 0.
        + EFFET_RANG_ETUDE * (e["Niveau_Etude_Max"].map(RANG_ETUDE).fillna(4).to_numpy() - 4)
        + e["Cat_Ecole_Max"].map(EFFET_ECOLE).fillna(0).to_numpy()
        + np.minimum(EFFET_EXPERIENCE_AVANT * avant, EFFET_EXPERIENCE_AVANT_MAX)
        + EFFET_HOT_JOB * e["Hot_job"].to_numpy()
        + PART_MARCHE * np.log(e["Median"].to_numpy() / e["Mid"].to_numpy())
        + EFFET_FEMME * (e["Sexe"] == "F").to_numpy()
    ).astype(float)
    # On recentre : le Compa-Ratio moyen de l'entreprise vaut CR_MOYEN, quels que soient les effets.
    effets = effets - effets.mean() + np.log(CR_MOYEN)
    # La part de hasard. Un salaire qui sortirait de la grille est retire au sort (ce fichier est
    # « sans anomalie », comme celui de generate_sources.py) ; au bout de 50 essais,
    # le salaire est ramene a la borne.
    compa_ratio = np.exp(effets + rng.normal(0, BRUIT, size=n))
    for _ in range(50):
        dehors = (compa_ratio < MIN_RATIO) | (compa_ratio > MAX_RATIO)
        if not dehors.any():
            break
        compa_ratio[dehors] = np.exp(effets[dehors] + rng.normal(0, BRUIT, size=int(dehors.sum())))
    fixe = (e["Mid"].to_numpy() * compa_ratio).round(2)
    fixe = np.clip(fixe, e["Min"].to_numpy(), e["Max"].to_numpy())

    # Les outliers positifs : quelques salaries, tires au sort, passent au-dessus du Max de leur
    # grille (voir le point 10 des parametres).
    # Pourquoi un tirage a part (graine SEED + 3) et pas « rng » : les autres salaires restent
    # exactement ceux d'avant. Seuls les salaries tires changent.
    # Pourquoi au hasard et pas d'apres le profil : dans les vraies donnees, ces depassements
    # viennent de l'histoire de chacun (negociation, ancien statut), que le fichier ne dit pas.
    n_hauts = int(round(PART_OUTLIERS_POSITIFS * n))
    if n_hauts:
        rng_hauts = np.random.default_rng(SEED + 3)
        hauts = rng_hauts.choice(n, size=n_hauts, replace=False)
        depassement = rng_hauts.uniform(DEPASSEMENT_MIN, DEPASSEMENT_MAX, size=n_hauts)
        fixe[hauts] = (e["Max"].to_numpy()[hauts] * (1 + depassement)).round(2)
    return fixe


def main():
    # Cree le generateur aleatoire, initialise avec la graine SEED.
    # Tous les tirages aleatoires du script passent par rng.
    rng = np.random.default_rng(SEED)

    # ------------------------------------------------------------------
    # 1. BANDS
    # ------------------------------------------------------------------
    # Liste qui va recevoir une ligne (dictionnaire) par couple famille x niveau.
    bands_rows = []
    # Boucle sur chacune des 13 familles.
    for fam in FAMILLES:
        # Calcule les Mid des niveaux 1 a 7 pour cette famille.
        mids = mid_par_niveau(fam)
        # Boucle sur chacun des 7 niveaux.
        for g in NIVEAUX:
            # Mid (point milieu) de la bande pour ce niveau.
            mid = mids[g]
            # Ajoute une ligne a la table des bandes.
            bands_rows.append({
                "Pays": PAYS,
                "Job_Family": fam,
                "Niveau": g,
                # Borne basse : Mid x 0.67, arrondie a 2 decimales.
                "Min": round(mid * MIN_RATIO, 2),
                # Point milieu arrondi a 2 decimales.
                "Mid": round(mid, 2),
                # Borne haute : Mid x 1.33, arrondie a 2 decimales.
                "Max": round(mid * MAX_RATIO, 2),
                "Devise": DEVISE,
            })
    # Transforme la liste de dictionnaires en tableau pandas (13 x 7 = 91 lignes).
    bands = pd.DataFrame(bands_rows)

    # ------------------------------------------------------------------
    # 2. MARKET
    # ------------------------------------------------------------------
    # Liste qui va recevoir une ligne par couple famille x niveau pour le marche.
    market_rows = []
    # Boucle sur chacune des 13 familles.
    for fam in FAMILLES:
        # Recalcule les Mid internes de la famille (base de la reference marche).
        mids = mid_par_niveau(fam)
        # Boucle sur chacun des 7 niveaux.
        for g in NIVEAUX:
            # Mediane du marche = Mid interne x decalage de la famille x petit ecart propre au niveau.
            med = mids[g] * MARKET_SHIFT[fam] * (1 + rng.uniform(-MARKET_ECART_NIVEAU, MARKET_ECART_NIVEAU))
            # Ajoute une ligne a la table marche.
            market_rows.append({
                "Pays": PAYS,
                "Job_Family": fam,
                "Niveau": g,
                # 25e percentile du marche : Median x 0.66.
                "P25": round(med * P25_RATIO, 2),
                # Mediane du marche.
                "Median": round(med, 2),
                # 75e percentile du marche : Median x 1.33.
                "P75": round(med * P75_RATIO, 2),
                "Devise": DEVISE,
            })
    # Transforme la liste en tableau pandas (91 lignes).
    market = pd.DataFrame(market_rows)

    # ------------------------------------------------------------------
    # 3. EMPLOYES
    # ------------------------------------------------------------------
    # Calcule combien d'employes generer dans chaque famille
    # (ex. {"RETAIL BANKING": 5000, "IT": 1200, ...} pour N_EMPLOYES = 10000).
    effectifs = repartir(N_EMPLOYES, EFFECTIFS_10K)

    # 3a. Famille et niveau de chaque employe
    # Trois listes lues en parallele : la position k decrit le k-ieme employe
    # (sa famille, son niveau, et s'il occupe le poste commun RETAIL BANKING).
    # On remplit d'abord ces listes pour tout le monde : il faut connaitre
    # l'effectif de chaque couple famille x niveau avant de creer les postes.
    fam_emp, niveau_emp, commun_emp = [], [], []
    # Boucle sur chaque famille et son nombre d'employes n.
    for fam, n in effectifs.items():
        # Si la famille n'a aucun employe (possible avec un petit N_EMPLOYES), on passe.
        if n == 0:
            continue
        # Tire au hasard n niveaux selon la pyramide POIDS_NIVEAU.
        # La division par la somme garantit que les probabilites totalisent 1.
        niveaux_fam = rng.choice(NIVEAUX, size=n, p=POIDS_NIVEAU / POIDS_NIVEAU.sum())

        # 40% des effectifs RETAIL BANKING partagent un meme poste
        if fam == "RETAIL BANKING":
            # Nombre d'employes qui auront le poste commun (40% de n, arrondi).
            n_unique = int(round(n * RETAIL_TITRE_UNIQUE_PART))
            # Tire au hasard, sans doublon, les positions (0..n-1) de ces employes.
            # On les stocke dans un set pour tester rapidement "i in idx_unique".
            idx_unique = set(rng.choice(n, size=n_unique, replace=False).tolist())
        else:
            # Pour les autres familles, aucun employe n'a le poste commun.
            idx_unique = set()

        # Ajoute les n employes de la famille aux trois listes.
        for i in range(n):
            fam_emp.append(fam)
            # Niveau converti en entier Python standard.
            niveau_emp.append(int(niveaux_fam[i]))
            # True si cet employe fait partie des 40% au poste commun.
            commun_emp.append(i in idx_unique)

    # 3b. Postes (Job_Title) et Hot_job
    # Numero de poste de chaque employe, dans le meme ordre que fam_emp.
    poste_emp = attribuer_postes(fam_emp, niveau_emp, commun_emp, rng)
    # Nombre d'employes par poste, ex. {1: 2000, 2: 5, 3: 3, ...}.
    taille_poste = Counter(poste_emp)
    # Hot_job de chaque poste, ex. {1: 0, 2: 2, 3: 1, ...}.
    hot_poste = attribuer_hot_job(taille_poste, rng)

    # 3c. Autres attributs, employe par employe
    # Liste qui va recevoir une ligne par employe.
    emp_rows = []
    # Compteur servant a numeroter les matricules (Mat00001, Mat00002, ...).
    matricule = 1
    # Boucle sur chaque employe : sa famille, son niveau et son numero de poste.
    for fam, g, poste in zip(fam_emp, niveau_emp, poste_emp):
        # Pole / entite
        # Pole de la famille ; si None (TRANSVERSE), on tire un pole entre 1 et 5.
        # (rng.integers(1, 6) renvoie un entier de 1 a 5, 6 exclu.)
        pole = POLE_MAP[fam] or int(rng.integers(1, 6))
        # Tire une entite N2 au hasard dans ce pole, ex. "P3-E07".
        # :02d ecrit le numero sur 2 chiffres avec un zero devant si besoin.
        entite = f"P{pole}-E{int(rng.integers(1, N_ENTITES_N2[pole] + 1)):02d}"

        # Le salaire, l'age et l'anciennete ne sont pas tires ici : ils dependent du diplome et
        # de la performance, connus plus bas (etapes 3e et 3f). Les trois colonnes sont creees
        # vides pour garder leur place dans le fichier.

        # Ajoute la ligne complete de l'employe.
        emp_rows.append({
            # Identifiant provisoire sur 5 chiffres, ex. "Mat00042".
            "Matricule": f"Mat{matricule:05d}",
            # Nom anonymise (donnees fictives).
            "Nom": "nan",
            # Entite N1 = le pole, ex. "Pole 3".
            "Entite_N1": f"Pole {pole}",
            # Entite N2 tiree plus haut, ex. "P3-E07".
            "Entite_N2": entite,
            "Pays": PAYS,
            "Job_Family": fam,
            # Numero de poste sur 4 chiffres, ex. "JT0042".
            "Job_Title": f"JT{poste:04d}",
            "Niveau": g,
            # Salaire fixe annuel en MAD, age et anciennete : remplis aux etapes 3e et 3f.
            "Fixe_Annuel_MAD": np.nan,
            "Age": 0,
            "Anciennete": 0,
            # Tire un nombre entre 0 et 1 : s'il est < 0.46 -> femme, sinon homme.
            "Sexe": "F" if rng.random() < PART_FEMMES else "M",
            # Equivalent temps plein : 1 = temps plein pour tout le monde.
            "FTE": 1,
            "Devise": DEVISE,
            "Date_Effet_Paie": DATE_EFFET,
            # Note de competence : loi normale bornee entre 0 et 5, arrondie a 2 decimales.
            "Competence_N1": round(float(np.clip(rng.normal(COMP_MU, COMP_SD), 0, 5)), 2),
            # Hot_job herite du poste : de 0 (metier peu tendu) a 2 (tres tendu).
            "Hot_job": hot_poste[poste],
        })
        # Passe au numero de matricule suivant.
        matricule += 1

    # Transforme la liste des employes en tableau pandas.
    employes = pd.DataFrame(emp_rows)
    # Melange aleatoirement toutes les lignes (frac=1 = 100% des lignes)
    # pour que les employes ne soient plus regroupes par famille,
    # puis renumerote l'index de 0 a N-1 (drop=True jette l'ancien index).
    employes = employes.sample(frac=1, random_state=SEED).reset_index(drop=True)
    # Reattribue les matricules dans le nouvel ordre : Mat00001, Mat00002, ...
    employes["Matricule"] = [f"Mat{i:05d}" for i in range(1, len(employes) + 1)]

    # 3d. Diplome, performance N-1 et positionnement 9-Box
    # Un tirage au sort a part (graine SEED + 2) pour tout ce qui se calcule apres la boucle.
    rng_ajouts = np.random.default_rng(SEED + 2)
    n = len(employes)

    # Diplome : le nombre exact de salaries par couple (niveau d'etudes, categorie), donnes en
    # priorite aux postes et aux metiers qui recrutent le plus diplome (voir attribuer_diplomes).
    employes["Niveau_Etude_Max"], employes["Cat_Ecole_Max"] = attribuer_diplomes(employes, rng_ajouts)

    # Performance : un score = une part de la competence (centree, ramenee a l'ecart-type 1)
    # + une part de hasard. Les salaries sont ensuite ranges par score : les 5 % les plus bas
    # recoivent « Tres en dessous », les 15 % suivants « Proche de l'objectif », etc.
    # Pourquoi ranger plutot que couper a des seuils fixes : on obtient exactement les parts
    # de PARTS_PERFORMANCE.
    comp = (employes["Competence_N1"].to_numpy() - COMP_MU) / COMP_SD
    score = LIEN_PERF_COMP * comp + np.sqrt(1 - LIEN_PERF_COMP ** 2) * rng_ajouts.normal(size=n)
    n_perf = repartir(n, PARTS_PERFORMANCE)
    libelles = np.repeat(list(n_perf), list(n_perf.values()))
    performance = np.empty(n, dtype=object)
    performance[np.argsort(score, kind="stable")] = libelles
    employes["Performance_N1"] = performance
    # Le positionnement 9-Box, avec la formule des RH (voir positionnement_9box).
    employes["Positionnement_9BOX"] = [positionnement_9box(p, c) for p, c in
                                       zip(employes["Performance_N1"], employes["Competence_N1"])]

    # 3e. Age et anciennete, reconstruits a partir du niveau d'etudes et du niveau du poste.
    employes["Age"], employes["Anciennete"] = attribuer_age_anciennete(employes, rng_ajouts)

    # 3f. Le salaire, en dernier : il depend de tout le profil.
    employes["Fixe_Annuel_MAD"] = calculer_salaires(employes, bands, market, rng_ajouts)

    # Ordre des colonnes : le diplome juste apres le niveau, la performance juste apres
    # la competence (meme ordre que le fichier des salaries utilise jusqu'ici).
    colonnes = [c for c in employes.columns
                if c not in ("Niveau_Etude_Max", "Cat_Ecole_Max", "Performance_N1", "Positionnement_9BOX")]
    colonnes[colonnes.index("Niveau") + 1:colonnes.index("Niveau") + 1] = ["Niveau_Etude_Max", "Cat_Ecole_Max"]
    colonnes[colonnes.index("Competence_N1") + 1:colonnes.index("Competence_N1") + 1] = ["Performance_N1", "Positionnement_9BOX"]
    employes = employes[colonnes]

    # ------------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------------
    # Racine du projet = dossier parent de src/ (ce script vit dans src/,
    # les donnees dans input/, meme convention que debug_cohort.py).
    # __file__ = chemin de ce script ; .parent = src/ ; .parent.parent = racine.
    base_dir = Path(__file__).resolve().parent.parent
    # Dossier de sortie : <racine>/input.
    out_dir = base_dir / "input"
    # Cree le dossier s'il n'existe pas (sans erreur s'il existe deja).
    out_dir.mkdir(parents=True, exist_ok=True)

    # Fichiers Excel (.xlsx), lus tels quels par src/anomaly_pretraitement.py.
    # Liste des chemins des fichiers ecrits, pour les afficher ensuite.
    paths = []
    # Boucle sur les 3 tables avec le nom de fichier associe.
    for df, nom in [(bands, "bands"), (employes, "employes"), (market, "market")]:
        # Chemin complet du fichier, ex. input/bands.xlsx.
        xlsx_path = out_dir / f"{nom}.xlsx"
        # Ecrit le tableau en Excel, sans la colonne d'index. Plus de separateur
        # ni d'encodage a choisir : un .xlsx s'ouvre tel quel dans Excel.
        df.to_excel(xlsx_path, index=False)
        # Memorise le chemin sous forme de texte.
        paths.append(str(xlsx_path))

    # Affiche le dossier de sortie et la liste des fichiers generes.
    print("Fichiers generes dans :", out_dir)
    for p in paths:
        print(" -", p)
    # Affiche la taille (lignes, colonnes) de chaque table.
    print("\nbands :", bands.shape, "| employes :", employes.shape, "| market :", market.shape)
    # Affiche le nombre d'employes par famille, du plus grand au plus petit.
    print("\nEffectifs par famille :")
    print(employes.Job_Family.value_counts().to_string())
    # Controles de coherence : chaque ligne doit afficher True (ou N_POSTES pour les postes).
    print("\nControles :")
    # Verifie que TOUS les employes respectent Age - Anciennete >= 18.
    print("  Age - Anciennete >= 18 :", bool(((employes.Age - employes.Anciennete) >= ECART_AGE_ANC_MIN).all()))
    print("  Age <= 60 :", bool((employes.Age <= AGE_MAX).all()))
    # Joint chaque employe a sa bande (meme pays, famille, niveau) pour recuperer Min et Max.
    ctrl = employes.merge(bands, on=["Pays", "Job_Family", "Niveau"])
    # Verifie qu'AUCUN salaire n'est sous le Min de sa bande, et compte ceux qui depassent le Max :
    # ce nombre doit etre celui des outliers positifs demandes (PART_OUTLIERS_POSITIFS).
    print("  Aucun salaire sous le Min :", bool((ctrl.Fixe_Annuel_MAD >= ctrl.Min).all()))
    print("  Salaires au-dessus du Max (outliers positifs) :", int((ctrl.Fixe_Annuel_MAD > ctrl.Max).sum()),
          "| demandes :", int(round(PART_OUTLIERS_POSITIFS * len(employes))))
    # Compte les postes differents (doit valoir N_POSTES).
    print("  Postes distincts :", employes.Job_Title.nunique())
    # Verifie que chaque poste appartient a une seule famille.
    print("  Une seule famille par poste :",
          bool((employes.groupby("Job_Title").Job_Family.nunique() == 1).all()))
    # Verifie que tous les employes d'un meme poste ont le meme Hot_job.
    print("  Un seul Hot_job par poste :",
          bool((employes.groupby("Job_Title").Hot_job.nunique() == 1).all()))
    # Verifie qu'aucun matricule n'apparait deux fois.
    print("  Matricules uniques :", employes.Matricule.is_unique)

    # Le profil moyen par niveau : l'age et l'anciennete montent nettement avec le niveau, le
    # Compa-Ratio beaucoup moins (on entre en bas de la grille a chaque promotion).
    ctrl["Compa_Ratio"] = ctrl.Fixe_Annuel_MAD / ctrl.Mid
    print("\nPar niveau : salaries | age moyen | anciennete moyenne | Compa-Ratio moyen")
    for g, d in ctrl.groupby("Niveau"):
        print(f"  {g} : {len(d):5d} | {d.Age.mean():5.1f} | {d.Anciennete.mean():5.1f} | {d.Compa_Ratio.mean():.2f}")
    print(f"  Compa-Ratio : de {ctrl.Compa_Ratio.min():.2f} a {ctrl.Compa_Ratio.max():.2f}, moyenne {ctrl.Compa_Ratio.mean():.2f}")
    print(f"  Lien age / anciennete (correlation) : {employes.Age.corr(employes.Anciennete):.2f}")

    # Compare la repartition obtenue du Hot_job a la cible, cote employes et cote postes.
    print("\nHot_job : % employes | % postes | cible")
    # Part des employes dans chaque valeur (normalize=True donne des proportions).
    pct_emp = employes.Hot_job.value_counts(normalize=True)
    # drop_duplicates garde une ligne par poste : on compte alors les postes.
    pct_postes = employes.drop_duplicates("Job_Title").Hot_job.value_counts(normalize=True)
    total = sum(HOT_JOB_PARTS.values())
    for h, p in HOT_JOB_PARTS.items():
        print(f"  {h} : {pct_emp.get(h, 0):7.1%} | {pct_postes.get(h, 0):7.1%} | {p / total:7.1%}")

    # Part de chaque niveau d'etudes et de chaque performance N-1.
    print("\nNiveau d'etudes : % employes")
    print(employes.Niveau_Etude_Max.value_counts(normalize=True).map("{:7.1%}".format).to_string())
    print("\nPerformance N-1 : % employes | cible | competence moyenne")
    pct_perf = employes.Performance_N1.value_counts(normalize=True)
    comp_perf = employes.groupby("Performance_N1").Competence_N1.mean()
    for lib, p in PARTS_PERFORMANCE.items():
        print(f"  {lib:24} : {pct_perf.get(lib, 0):7.1%} | {p:7.1%} | {comp_perf.get(lib, float('nan')):.2f}")

    # Part de chaque categorie 9-Box : elle n'a pas de cible, elle decoule de la formule.
    print("\n9-Box : % employes")
    print(employes.Positionnement_9BOX.value_counts(normalize=True).map("{:7.1%}".format).to_string())


# Ce bloc ne s'execute que si on lance directement le fichier
# (python src/generate_sources_realiste.py), pas quand on l'importe depuis un autre module.
if __name__ == "__main__":
    main()
