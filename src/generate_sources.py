"""
Generation des 3 tables sources : bands, employes, market_shifted.
Conforme a la spec "Specification de la generation de donnees" (v finale, sept. 2026).

Tous les parametres ajustables sont regroupes dans la section PARAMETRES.
Pour passer de l'echantillon a la volumetrie cible : N_EMPLOYES = 10000.

Vue d'ensemble de ce que fait le script :
  1. BANDS    : pour chaque famille de metiers et chaque grade (1 a 7), calcule
                une grille salariale interne (Min / Mid / Max).
  2. MARKET   : pour les memes couples famille x grade, calcule les references
                du marche (P25 / Median / P75), derivees de la grille interne.
  3. EMPLOYES : genere des employes fictifs (famille, grade, poste, salaire,
                age, anciennete, sexe, etc.) dont le salaire tombe dans la
                bande. Les postes sont de simples numeros (JT0001, JT0002...)
                et chacun porte un Hot_job de 0 a 6.
  4. EXPORT   : ecrit les 3 tables en CSV dans le dossier input/ et affiche
                quelques controles de coherence.
"""

# Counter compte les occurrences d'une liste, ex. Counter([1, 1, 2]) -> {1: 2, 2: 1}.
from collections import Counter
# Path permet de manipuler les chemins de fichiers de facon portable (Windows / Linux).
from pathlib import Path

# numpy : calcul numerique et tirages aleatoires (loi normale, uniforme, choix...).
import numpy as np
# pandas : manipulation de tableaux de donnees (DataFrame) et export CSV.
import pandas as pd

# ----------------------------------------------------------------------------
# PARAMETRES
# ----------------------------------------------------------------------------
# Graine du generateur aleatoire : avec la meme graine, le script produit
# exactement les memes donnees a chaque execution (reproductibilite).
SEED = 20260909
# Nombre total d'employes a generer.
N_EMPLOYES = 10000            # <-- mettre 10000 pour la volumetrie cible
# Liste des grades [1, 2, 3, 4, 5, 6, 7] ; range(1, 8) s'arrete avant 8.
GRADES = list(range(1, 8))  # 1 = plus eleve, 7 = plus bas
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

# Ancrage : valeur du Mid au grade 7.
# C'est le point de depart de la grille : tous les autres grades sont
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

# Coefficient de progression inter-grade, fixe par l'ancrage du grade 7 :
# les familles ancrees a 126 prennent 1.30, celles ancrees a 200 (IT, DATA) 1.25.
# Exemple : avec 1.30, le Mid du grade 6 = Mid du grade 7 x 1.30,
# le Mid du grade 5 = Mid du grade 6 x 1.30, etc.
COEF_PAR_ANCRAGE = {126.0: 1.30, 200.0: 1.25}
# Coefficient de chaque famille, lu a partir de son ancrage : on ne peut pas
# changer l'ancrage d'une famille sans que son coefficient suive.
COEF = {f: COEF_PAR_ANCRAGE[ANCRAGE_G7[f]] for f in FAMILLES}

# Bornes de la bande interne : Min = Mid x 0.67, Max = Mid x 1.33.
MIN_RATIO, MAX_RATIO = 0.67, 1.33      # Mid -/+ 33%
# Bornes du marche : P25 = Median x 0.66, P75 = Median x 1.33.
P25_RATIO, P75_RATIO = 0.66, 1.33      # market_shifted

# Decalage marche vs interne. 1.00 = spec litterale (Median == Mid).
# Dictionnaire construit en comprehension : chaque famille -> 1.00.
# Mettre par ex. 1.10 pour une famille dont le marche paie 10% de plus.
# Ce parametre permet de simuler un cas plus realiste. Par exemple, les metiers
# IT et DATA sont souvent mieux payes ailleurs. Pour le reproduire, on peut ecrire :
#     MARKET_SHIFT = {f: 1.00 for f in FAMILLES}
#     MARKET_SHIFT["IT"] = 1.15
#     MARKET_SHIFT["DATA"] = 1.15
MARKET_SHIFT = {f: 1.00 for f in FAMILLES}

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
# Nombre d'entites de niveau 2 (sous-directions) dans chaque pole.
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
# Hot_job : tension du metier sur le marche, de 0 (faible) a 6 (forte).
# Part des employes visee pour chaque valeur (total = 100%).
# Tous les employes d'un meme poste ont le meme Hot_job.
HOT_JOB_PARTS = {0: 0.14, 1: 0.06, 2: 0.35, 3: 0.03, 4: 0.21, 5: 0.14, 6: 0.07}

# Distribution des grades : identique pour toutes les familles (pyramide)
# Probabilite d'avoir le grade 1, 2, ..., 7 (peu de directeurs, beaucoup de juniors).
POIDS_GRADE = np.array([0.04, 0.07, 0.11, 0.17, 0.22, 0.22, 0.17])

# Age : loi normale de moyenne 37 ans, ecart-type 8, bornee entre 20 et 60.
AGE_MU, AGE_SD, AGE_MIN, AGE_MAX = 37, 8, 20, 60
# Anciennete (en annees) : moyenne 5, ecart-type 4, bornee entre 0 et 40.
ANC_MU, ANC_SD, ANC_MIN, ANC_MAX = 5, 4, 0, 40
# Contrainte de realisme : on ne peut pas etre entre avant 18 ans
# (Age - Anciennete doit etre >= 18).
ECART_AGE_ANC_MIN = 18
# Probabilite qu'un employe soit une femme (46%).
PART_FEMMES = 0.46
# Note de competence : loi normale de moyenne 3.35 et ecart-type 0.60 (sur 5).
COMP_MU, COMP_SD = 3.35, 0.60

# ----------------------------------------------------------------------------
# 1. BANDS
# ----------------------------------------------------------------------------
def mid_par_grade(famille):
    """Mid(grade) = Mid(grade+1) x coef, en remontant du grade 7 au grade 1."""
    # Recupere le coefficient de progression de la famille (ex. 1.30).
    coef = COEF[famille]
    # Initialise le dictionnaire {grade: mid} avec la valeur d'ancrage du grade 7.
    mids = {7: ANCRAGE_G7[famille]}
    # Parcourt les grades 6, 5, 4, 3, 2, 1 (range(6, 0, -1) descend jusqu'a 1).
    for g in range(6, 0, -1):
        # Le Mid du grade g = Mid du grade juste en dessous (g + 1) x coef.
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
# grade, sauf le poste commun RETAIL BANKING qui melange les grades.
# Les N_POSTES postes sont partages entre les couples famille x grade selon
# leur effectif : une cellule de 400 employes a plus de postes qu'une de 10.
# Chaque poste recoit au moins un employe, pour retrouver exactement
# N_POSTES intitules differents dans employes.csv.
def attribuer_postes(fam_emp, grade_emp, commun_emp, rng):
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

    # Regroupe les autres employes par cellule famille x grade :
    # {("IT", 5): [positions des employes IT de grade 5], ...}.
    cellules = {}
    for k, (fam, g, commun) in enumerate(zip(fam_emp, grade_emp, commun_emp)):
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

    # Parcourt les cellules dans l'ordre (famille, puis grade) pour numeroter les postes.
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


# attribuer_hot_job : donne a chaque poste un Hot_job de 0 a 6 ; tous les
# employes du poste heritent de cette valeur. Les parts de HOT_JOB_PARTS sont
# visees sur les EMPLOYES (ce qu'on lit dans employes.csv), pas sur les postes :
# le poste commun RETAIL BANKING (2000 employes) pese 2000, pas 1.
# Methode : on prend les postes du plus gros au plus petit, et chacun va dans
# la valeur la moins remplie par rapport a sa cible, a condition d'y tenir.
# Exemple : le poste commun (2000) ne tient que dans 2 (cible 3500) ou 4 (2100) ;
# il va dans 2, qui a le plus de place. Les autres postes (quelques employes
# chacun) remplissent ensuite toutes les valeurs au meme rythme.
def attribuer_hot_job(taille_poste, rng):
    """Renvoie {numero de poste: Hot_job}."""
    # Somme des parts (1.00), pour tolerer des parts qui ne tomberaient pas pile a 100%.
    total = sum(HOT_JOB_PARTS.values())
    # Nombre total d'employes (somme des tailles de postes).
    n_emp = sum(taille_poste.values())
    # Nombre d'employes vise par valeur, ex. 35% x 10000 = 3500 pour Hot_job = 2.
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

def main():
    # Cree le generateur aleatoire, initialise avec la graine SEED.
    # Tous les tirages aleatoires du script passent par rng.
    rng = np.random.default_rng(SEED)

    # ------------------------------------------------------------------
    # 1. BANDS
    # ------------------------------------------------------------------
    # Liste qui va recevoir une ligne (dictionnaire) par couple famille x grade.
    bands_rows = []
    # Boucle sur chacune des 13 familles.
    for fam in FAMILLES:
        # Calcule les Mid des grades 1 a 7 pour cette famille.
        mids = mid_par_grade(fam)
        # Boucle sur chacun des 7 grades.
        for g in GRADES:
            # Mid (point milieu) de la bande pour ce grade.
            mid = mids[g]
            # Ajoute une ligne a la table des bandes.
            bands_rows.append({
                "Pays": PAYS,
                "Job_Family": fam,
                "Grade": g,
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
    # Liste qui va recevoir une ligne par couple famille x grade pour le marche.
    market_rows = []
    # Boucle sur chacune des 13 familles.
    for fam in FAMILLES:
        # Recalcule les Mid internes de la famille (base de la reference marche).
        mids = mid_par_grade(fam)
        # Boucle sur chacun des 7 grades.
        for g in GRADES:
            # Mediane du marche = Mid interne x decalage marche (1.00 par defaut).
            med = mids[g] * MARKET_SHIFT[fam]
            # Ajoute une ligne a la table marche.
            market_rows.append({
                "Pays": PAYS,
                "Job_Family": fam,
                "Grade": g,
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

    # 3a. Famille et grade de chaque employe
    # Trois listes lues en parallele : la position k decrit le k-ieme employe
    # (sa famille, son grade, et s'il occupe le poste commun RETAIL BANKING).
    # On remplit d'abord ces listes pour tout le monde : il faut connaitre
    # l'effectif de chaque couple famille x grade avant de creer les postes.
    fam_emp, grade_emp, commun_emp = [], [], []
    # Boucle sur chaque famille et son nombre d'employes n.
    for fam, n in effectifs.items():
        # Si la famille n'a aucun employe (possible avec un petit N_EMPLOYES), on passe.
        if n == 0:
            continue
        # Tire au hasard n grades selon la pyramide POIDS_GRADE.
        # La division par la somme garantit que les probabilites totalisent 1.
        grades_fam = rng.choice(GRADES, size=n, p=POIDS_GRADE / POIDS_GRADE.sum())

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
            # Grade converti en entier Python standard.
            grade_emp.append(int(grades_fam[i]))
            # True si cet employe fait partie des 40% au poste commun.
            commun_emp.append(i in idx_unique)

    # 3b. Postes (Job_Title) et Hot_job
    # Numero de poste de chaque employe, dans le meme ordre que fam_emp.
    poste_emp = attribuer_postes(fam_emp, grade_emp, commun_emp, rng)
    # Nombre d'employes par poste, ex. {1: 2000, 2: 5, 3: 3, ...}.
    taille_poste = Counter(poste_emp)
    # Hot_job de chaque poste, ex. {1: 2, 2: 0, 3: 4, ...}.
    hot_poste = attribuer_hot_job(taille_poste, rng)

    # 3c. Autres attributs, employe par employe
    # Liste qui va recevoir une ligne par employe.
    emp_rows = []
    # Compteur servant a numeroter les matricules (Mat00001, Mat00002, ...).
    matricule = 1
    # Boucle sur chaque employe : sa famille, son grade et son numero de poste.
    for fam, g, poste in zip(fam_emp, grade_emp, poste_emp):
        # Pole / entite
        # Pole de la famille ; si None (TRANSVERSE), on tire un pole entre 1 et 5.
        # (rng.integers(1, 6) renvoie un entier de 1 a 5, 6 exclu.)
        pole = POLE_MAP[fam] or int(rng.integers(1, 6))
        # Tire une entite de niveau 2 au hasard dans ce pole, ex. "P3-E07".
        # :02d ecrit le numero sur 2 chiffres avec un zero devant si besoin.
        entite = f"P{pole}-E{int(rng.integers(1, N_ENTITES_N2[pole] + 1)):02d}"

        # Salaire dans la fourchette [Min, Max] de la bande Famille x Grade
        # Selectionne dans bands la ligne correspondant a cette famille et ce grade.
        b = bands[(bands.Job_Family == fam) & (bands.Grade == g)].iloc[0]
        # Tire un salaire uniformement entre Min et Max, arrondi a 2 decimales.
        fixe = round(float(rng.uniform(b.Min, b.Max)), 2)

        # Age / anciennete sous contrainte Age - Anciennete >= 18
        # On retire au sort tant que la contrainte n'est pas respectee.
        while True:
            # Age tire selon une loi normale, arrondi, puis borne entre 20 et 60.
            age = int(np.clip(round(rng.normal(AGE_MU, AGE_SD)), AGE_MIN, AGE_MAX))
            # Anciennete tiree selon une loi normale, arrondie, puis bornee entre 0 et 40.
            anc = int(np.clip(round(rng.normal(ANC_MU, ANC_SD)), ANC_MIN, ANC_MAX))
            # Si l'employe avait au moins 18 ans a son embauche, on garde ce tirage.
            if age - anc >= ECART_AGE_ANC_MIN:
                break

        # Ajoute la ligne complete de l'employe.
        emp_rows.append({
            # Identifiant provisoire sur 5 chiffres, ex. "Mat00042".
            "Matricule": f"Mat{matricule:05d}",
            # Nom anonymise (donnees fictives).
            "Nom": "nan",
            # Entite de niveau 1 = le pole, ex. "Pole 3".
            "Entite_N1": f"Pole {pole}",
            # Entite de niveau 2 tiree plus haut, ex. "P3-E07".
            "Entite_N2": entite,
            "Pays": PAYS,
            "Job_Family": fam,
            # Numero de poste sur 4 chiffres, ex. "JT0042".
            "Job_Title": f"JT{poste:04d}",
            "Grade": g,
            # Salaire fixe annuel en MAD.
            "Fixe_Annuel_MAD": fixe,
            "Age": age,
            "Anciennete": anc,
            # Tire un nombre entre 0 et 1 : s'il est < 0.46 -> femme, sinon homme.
            "Sexe": "F" if rng.random() < PART_FEMMES else "M",
            # Equivalent temps plein : 1 = temps plein pour tout le monde.
            "FTE": 1,
            "Devise": DEVISE,
            "Date_Effet_Paie": DATE_EFFET,
            # Note de competence : loi normale bornee entre 0 et 5, arrondie a 2 decimales.
            "Competence_N1": round(float(np.clip(rng.normal(COMP_MU, COMP_SD), 0, 5)), 2),
            # Case de la matrice 9-Box (performance x potentiel), entier de 0 a 8.
            "Positionnement_9BOX": int(rng.integers(0, 9)),
            # Hot_job herite du poste : de 0 (metier peu tendu) a 6 (tres tendu).
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

    # CSV (point-virgule, encodage cp1252), au format attendu par
    # detect_salary_anomalies_custom_fixed.py --employees/--bands/--market.
    # Liste des chemins des fichiers ecrits, pour les afficher ensuite.
    paths = []
    # Boucle sur les 3 tables avec le nom de fichier associe.
    for df, nom in [(bands, "bands"), (employes, "employes"), (market, "market")]:
        # Chemin complet du fichier, ex. input/bands.csv.
        csv_path = out_dir / f"{nom}.csv"
        # Ecrit le tableau en CSV : separateur ";", sans la colonne d'index,
        # encodage cp1252 (compatible Excel francais sous Windows).
        df.to_csv(csv_path, sep=";", index=False, encoding="cp1252")
        # Memorise le chemin sous forme de texte.
        paths.append(str(csv_path))

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
    print("  Age - Anciennete >= 18 :", bool(((employes.Age - employes.Anciennete) >= 18).all()))
    # Joint chaque employe a sa bande (meme pays, famille, grade) pour recuperer Min et Max.
    ctrl = employes.merge(bands, on=["Pays", "Job_Family", "Grade"])
    # Verifie que TOUS les salaires sont compris entre Min et Max de leur bande.
    print("  Salaire dans [Min, Max] :",
          bool(((ctrl.Fixe_Annuel_MAD >= ctrl.Min) & (ctrl.Fixe_Annuel_MAD <= ctrl.Max)).all()))
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

    # Compare la repartition obtenue du Hot_job a la cible, cote employes et cote postes.
    print("\nHot_job : % employes | % postes | cible")
    # Part des employes dans chaque valeur (normalize=True donne des proportions).
    pct_emp = employes.Hot_job.value_counts(normalize=True)
    # drop_duplicates garde une ligne par poste : on compte alors les postes.
    pct_postes = employes.drop_duplicates("Job_Title").Hot_job.value_counts(normalize=True)
    total = sum(HOT_JOB_PARTS.values())
    for h, p in HOT_JOB_PARTS.items():
        print(f"  {h} : {pct_emp.get(h, 0):7.1%} | {pct_postes.get(h, 0):7.1%} | {p / total:7.1%}")


# Ce bloc ne s'execute que si on lance directement le fichier
# (python src/generate_sources.py), pas quand on l'importe depuis un autre module.
if __name__ == "__main__":
    main()
