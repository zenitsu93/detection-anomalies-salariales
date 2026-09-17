"""
Generation des 3 tables sources : bands, employes, market_shifted.
Conforme a la spec "Specification de la generation de donnees" (v finale, sept. 2026).

Tous les parametres ajustables sont regroupes dans la section PARAMETRES.
Pour passer de l'echantillon a la volumetrie cible : N_EMPLOYES = 10000.
"""

from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# PARAMETRES
# ----------------------------------------------------------------------------
SEED = 20260909
N_EMPLOYES = 10000            # <-- mettre 10000 pour la volumetrie cible
GRADES = list(range(1, 8))  # 1 = plus eleve, 7 = plus bas
PAYS = "Maroc"
DEVISE = "MAD"
DATE_EFFET = "01/08/2025"

FAMILLES = [
    "AUDIT", "COMMUNICATION", "CONFORMITE", "DATA", "FINANCE",
    "GESTION DES RISQUES", "IT", "RETAIL BANKING", "RH", "STRATEGIE",
    "TRANSFORMATION", "JURIDIQUE", "TRANSVERSE",
]

# Coefficient de progression inter-grade (fixe par famille)
COEF = {
    "AUDIT": 1.30, "CONFORMITE": 1.30, "GESTION DES RISQUES": 1.30,
    "JURIDIQUE": 1.30, "FINANCE": 1.30, "DATA": 1.30, "IT": 1.25,
    "RETAIL BANKING": 1.25, "RH": 1.25, "COMMUNICATION": 1.25,
    "STRATEGIE": 1.25, "TRANSFORMATION": 1.25, "TRANSVERSE": 1.25,
}

# Ancrage : valeur du Mid au grade 7.
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
ANCRAGE_FOURNI = {"AUDIT", "IT"}

MIN_RATIO, MAX_RATIO = 0.67, 1.33      # Mid -/+ 33%
P25_RATIO, P75_RATIO = 0.66, 1.33      # market_shifted

# Decalage marche vs interne. 1.00 = spec litterale (Median == Mid).
MARKET_SHIFT = {f: 1.00 for f in FAMILLES}

# Mapping famille -> pole
POLE_MAP = {
    "AUDIT": 1, "CONFORMITE": 1, "GESTION DES RISQUES": 1, "JURIDIQUE": 1,
    "RH": 2, "COMMUNICATION": 2, "STRATEGIE": 2,
    "RETAIL BANKING": 3,
    "FINANCE": 4, "IT": 4, "DATA": 4,
    "TRANSFORMATION": 5,
    "TRANSVERSE": None,  # aleatoire
}
N_ENTITES_N2 = {1: 15, 2: 7, 3: 20, 4: 13, 5: 17}

# Effectifs cibles sur 10 000 (repartition proportionnelle si N_EMPLOYES < 10000)
EFFECTIFS_10K = {
    "RETAIL BANKING": 5000, "IT": 1200, "FINANCE": 900,
    "GESTION DES RISQUES": 700, "RH": 500, "CONFORMITE": 400, "AUDIT": 300,
    "TRANSFORMATION": 250, "DATA": 200, "JURIDIQUE": 200,
    "COMMUNICATION": 150, "STRATEGIE": 100, "TRANSVERSE": 100,
}
# Part des effectifs RETAIL BANKING partageant un intitule unique (2000/5000)
RETAIL_TITRE_UNIQUE_PART = 0.40
RETAIL_TITRE_UNIQUE = "Charge de clientele particuliers"

# Distribution des grades : identique pour toutes les familles (pyramide)
POIDS_GRADE = np.array([0.04, 0.07, 0.11, 0.17, 0.22, 0.22, 0.17])

AGE_MU, AGE_SD, AGE_MIN, AGE_MAX = 37, 8, 20, 60
ANC_MU, ANC_SD, ANC_MIN, ANC_MAX = 5, 4, 0, 40
ECART_AGE_ANC_MIN = 18
PART_FEMMES = 0.46
COMP_MU, COMP_SD = 3.35, 0.60

# ----------------------------------------------------------------------------
# 1. BANDS
# ----------------------------------------------------------------------------
def mid_par_grade(famille):
    """Mid(grade) = Mid(grade+1) x coef, en remontant du grade 7 au grade 1."""
    coef = COEF[famille]
    mids = {7: ANCRAGE_G7[famille]}
    for g in range(6, 0, -1):
        mids[g] = mids[g + 1] * coef
    return mids


def repartir(n_total, poids_dict):
    """Repartition entiere proportionnelle (methode des plus forts restes)."""
    tot = sum(poids_dict.values())
    exact = {k: v / tot * n_total for k, v in poids_dict.items()}
    base = {k: int(np.floor(v)) for k, v in exact.items()}
    reste = n_total - sum(base.values())
    ordre = sorted(exact, key=lambda k: exact[k] - base[k], reverse=True)
    for k in ordre[:reste]:
        base[k] += 1
    return base


# Catalogue de libelles : niveau (lie au grade) x specialite (lie a la famille)
NIVEAUX = {
    1: ["Directeur", "Directeur Executif"],
    2: ["Directeur Adjoint", "Responsable Departement"],
    3: ["Responsable", "Manager"],
    4: ["Manager Adjoint", "Chef de Projet Senior"],
    5: ["Charge Senior", "Chef de Projet"],
    6: ["Charge", "Analyste"],
    7: ["Charge Junior", "Analyste Junior"],
}
SPECIALITES = {
    "AUDIT": ["Audit Interne", "Audit des Risques", "Inspection Generale"],
    "COMMUNICATION": ["Communication Interne", "Communication Institutionnelle", "Relations Presse"],
    "CONFORMITE": ["Conformite", "LCB-FT", "Controle Permanent"],
    "DATA": ["Data Science", "Data Engineering", "Business Intelligence"],
    "FINANCE": ["Controle de Gestion", "Comptabilite", "Tresorerie"],
    "GESTION DES RISQUES": ["Risques de Credit", "Risques Operationnels", "Risques de Marche"],
    "IT": ["Infrastructure IT", "Developpement Applicatif", "Securite des SI"],
    "RETAIL BANKING": ["Clientele Particuliers", "Clientele Professionnels", "Reseau Agences"],
    "RH": ["Ressources Humaines", "Developpement RH", "Remuneration"],
    "STRATEGIE": ["Strategie Groupe", "Planification Strategique", "Veille Concurrentielle"],
    "TRANSFORMATION": ["Transformation Digitale", "Excellence Operationnelle", "PMO"],
    "JURIDIQUE": ["Affaires Juridiques", "Contentieux", "Droit Bancaire"],
    "TRANSVERSE": ["Support Transverse", "Services Generaux", "Coordination"],
}

def main():
    rng = np.random.default_rng(SEED)

    # ------------------------------------------------------------------
    # 1. BANDS
    # ------------------------------------------------------------------
    bands_rows = []
    for fam in FAMILLES:
        mids = mid_par_grade(fam)
        for g in GRADES:
            mid = mids[g]
            bands_rows.append({
                "Pays": PAYS,
                "Job_Family": fam,
                "Grade": g,
                "Min": round(mid * MIN_RATIO, 2),
                "Mid": round(mid, 2),
                "Max": round(mid * MAX_RATIO, 2),
                "Devise": DEVISE,
            })
    bands = pd.DataFrame(bands_rows)

    # ------------------------------------------------------------------
    # 2. MARKET
    # ------------------------------------------------------------------
    market_rows = []
    for fam in FAMILLES:
        mids = mid_par_grade(fam)
        for g in GRADES:
            med = mids[g] * MARKET_SHIFT[fam]
            market_rows.append({
                "Pays": PAYS,
                "Job_Family": fam,
                "Grade": g,
                "P25": round(med * P25_RATIO, 2),
                "Median": round(med, 2),
                "P75": round(med * P75_RATIO, 2),
                "Devise": DEVISE,
            })
    market = pd.DataFrame(market_rows)

    # ------------------------------------------------------------------
    # 3. EMPLOYES
    # ------------------------------------------------------------------
    effectifs = repartir(N_EMPLOYES, EFFECTIFS_10K)

    emp_rows = []
    matricule = 1
    for fam, n in effectifs.items():
        if n == 0:
            continue
        grades_fam = rng.choice(GRADES, size=n, p=POIDS_GRADE / POIDS_GRADE.sum())

        # 40% des effectifs RETAIL BANKING partagent un intitule unique
        if fam == "RETAIL BANKING":
            n_unique = int(round(n * RETAIL_TITRE_UNIQUE_PART))
            idx_unique = set(rng.choice(n, size=n_unique, replace=False).tolist())
        else:
            idx_unique = set()

        for i in range(n):
            g = int(grades_fam[i])

            # Pole / entite
            pole = POLE_MAP[fam] or int(rng.integers(1, 6))
            entite = f"P{pole}-E{int(rng.integers(1, N_ENTITES_N2[pole] + 1)):02d}"

            # Job_Title coherent avec le grade
            if i in idx_unique:
                titre = RETAIL_TITRE_UNIQUE
            else:
                titre = f"{rng.choice(NIVEAUX[g])} {rng.choice(SPECIALITES[fam])}"

            # Salaire dans la fourchette [Min, Max] de la bande Famille x Grade
            b = bands[(bands.Job_Family == fam) & (bands.Grade == g)].iloc[0]
            fixe = round(float(rng.uniform(b.Min, b.Max)), 2)

            # Age / anciennete sous contrainte Age - Anciennete >= 18
            while True:
                age = int(np.clip(round(rng.normal(AGE_MU, AGE_SD)), AGE_MIN, AGE_MAX))
                anc = int(np.clip(round(rng.normal(ANC_MU, ANC_SD)), ANC_MIN, ANC_MAX))
                if age - anc >= ECART_AGE_ANC_MIN:
                    break

            # Hot_job : majorite 0/1, la valeur 2 quasi reservee a AUDIT et IT
            if fam in ("AUDIT", "IT"):
                hot = int(rng.choice([0, 1, 2], p=[0.45, 0.35, 0.20]))
            else:
                hot = int(rng.choice([0, 1, 2], p=[0.70, 0.295, 0.005]))

            emp_rows.append({
                "Matricule": f"Mat{matricule:05d}",
                "Nom": "nan",
                "Entite_N1": f"Pole {pole}",
                "Entite_N2": entite,
                "Pays": PAYS,
                "Job_Family": fam,
                "Job_Title": titre,
                "Grade": g,
                "Fixe_Annuel_MAD": fixe,
                "Age": age,
                "Anciennete": anc,
                "Sexe": "F" if rng.random() < PART_FEMMES else "M",
                "FTE": 1,
                "Devise": DEVISE,
                "Date_Effet_Paie": DATE_EFFET,
                "Competence_N1": round(float(np.clip(rng.normal(COMP_MU, COMP_SD), 0, 5)), 2),
                "Positionnement_9BOX": int(rng.integers(0, 9)),
                "Hot_job": hot,
            })
            matricule += 1

    employes = pd.DataFrame(emp_rows)
    employes = employes.sample(frac=1, random_state=SEED).reset_index(drop=True)
    employes["Matricule"] = [f"Mat{i:05d}" for i in range(1, len(employes) + 1)]

    # ------------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------------
    # Racine du projet = dossier parent de src/ (ce script vit dans src/,
    # les donnees dans input/, meme convention que debug_cohort.py).
    base_dir = Path(__file__).resolve().parent.parent
    out_dir = base_dir / "input"
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV (point-virgule, encodage cp1252), au format attendu par
    # detect_salary_anomalies_custom_fixed.py --employees/--bands/--market.
    paths = []
    for df, nom in [(bands, "bands"), (employes, "employes"), (market, "market")]:
        csv_path = out_dir / f"{nom}.csv"
        df.to_csv(csv_path, sep=";", index=False, encoding="cp1252")
        paths.append(str(csv_path))

    print("Fichiers generes dans :", out_dir)
    for p in paths:
        print(" -", p)
    print("\nbands :", bands.shape, "| employes :", employes.shape, "| market :", market.shape)
    print("\nEffectifs par famille :")
    print(employes.Job_Family.value_counts().to_string())
    print("\nControles :")
    print("  Age - Anciennete >= 18 :", bool(((employes.Age - employes.Anciennete) >= 18).all()))
    ctrl = employes.merge(bands, on=["Pays", "Job_Family", "Grade"])
    print("  Salaire dans [Min, Max] :",
          bool(((ctrl.Fixe_Annuel_MAD >= ctrl.Min) & (ctrl.Fixe_Annuel_MAD <= ctrl.Max)).all()))
    print("  Hot_job = 2 hors AUDIT/IT :",
          int(((employes.Hot_job == 2) & (~employes.Job_Family.isin(["AUDIT", "IT"]))).sum()))
    print("  Matricules uniques :", employes.Matricule.is_unique)


if __name__ == "__main__":
    main()
