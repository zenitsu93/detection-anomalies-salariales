#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BANC D'ESSAI : QUELLE IA TROUVE LE MIEUX LES SALAIRES ANORMAUX ?
================================================================

Pour juger une détection, il faut des anomalies dont on connaît la réponse. Ce banc d'essai en fabrique,
EN MÉMOIRE (il ne touche à aucun fichier de input/), puis compare les deux IA du projet :
- l'Isolation Forest (ml_methode: isolation_forest), qui repère les profils rares ;
- l'écart au salaire attendu (ml_methode: ecart_attendu), qui repère les salariés payés nettement moins
  que ce que leur poste et leur profil laissent attendre.

Deux jeux de données :
1. « Fichiers actuels » : input/ tel quel. Les anomalies connues sont les salaires sous le Min (ceux
   qu'ajoute src/generate_sources_anomalies.py) ; les salaires au-dessus du Max ne doivent PAS remonter.
   Limite : dans ces données fictives, le salaire est tiré au hasard dans la grille, sans lien avec
   l'ancienneté ni la performance ; il n'y a donc rien de « subtil » à trouver.
2. « Données réalistes » : les mêmes salariés, mais le salaire suit le profil comme dans une vraie
   entreprise (ancienneté +1,2 %/an, performance de -8 % à +8 %, diplôme, compétence, Hot job, plus un
   aléa de 7 %). On y ajoute 3 % d'anomalies SUBTILES : payés 12 à 20 % de moins qu'attendu, souvent
   encore dans leur grille, que les règles voient mal. Plus les mêmes anomalies grossières qu'en 1.

Les mesures, pour chaque IA :
- Précision moyenne (de 0 à 1) : en classant les salariés du score le plus haut au plus bas, à quel point
  les vraies anomalies arrivent en tête (1 = toutes avant tous les autres) ;
- Dans le top 5 % : combien de vraies anomalies, d'anomalies subtiles et de salaires au-dessus du Max
  (qui ne sont pas des anomalies) parmi les 5 % de scores les plus hauts ;
- La priorité finale (Severity) : combien de Critical / Major sont de vraies anomalies.

Utilisation, depuis le dossier du projet :
      python analyse_modeles/banc_essai_ia.py
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score

PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJET / "src"))

from anomaly_pretraitement import preparer_employes  # noqa: E402
from anomaly_cohortes import former_cohortes  # noqa: E402
from anomaly_regles import apply_rulebook  # noqa: E402
from anomaly_signal_iforest import ml_anomaly  # noqa: E402
from anomaly_signal_fort import apply_ml_strong_signal  # noqa: E402
from anomaly_score_general import aggregate_risk  # noqa: E402

ANOMALIES = ["subtil", "sous_min", "tres_bas"]


def donnees_realistes(df: pd.DataFrame, graine: int = 0) -> pd.DataFrame:
    """Les mêmes salariés, avec un salaire qui suit le profil, et des anomalies connues (colonne Label)."""
    rng = np.random.default_rng(graine)
    df = df.copy()
    effet_perf = {1: -.08, 2: -.03, 3: 0, 4: .04, 5: .08}
    log_salaire = (np.log(df.Mid) + 0.012 * (df.Anciennete - 5) + df.Rang_Performance.map(effet_perf).fillna(0)
                   + 0.02 * (df.Rang_Etude_Max.fillna(5) - 5) + 0.03 * (df.Competence_N1 - 3.35)
                   + 0.03 * (df.Hot_job - 1) + rng.normal(0, 0.07, len(df)))
    salaire = np.exp(log_salaire).clip(df.Min, df.Max)
    label = np.array(["normal"] * len(df), dtype=object)
    ordre, debut = rng.permutation(len(df)), 0
    # (nom, part des salariés, facteur bas, facteur haut, base : None = le salaire attendu, sinon la borne)
    for nom, part, bas, haut, base in [("subtil", .03, .80, .88, None), ("sous_min", .02, .75, .90, "Min"),
                                       ("tres_bas", .005, .45, .60, "Min"), ("au_dessus", .015, 1.1, 1.4, "Max")]:
        n = int(part * len(df))
        lignes = ordre[debut:debut + n]
        debut += n
        reference = salaire.iloc[lignes] if base is None else df[base].iloc[lignes]
        salaire.iloc[lignes] = (rng.uniform(bas, haut, n) * reference).to_numpy()
        label[lignes] = nom
    df["Fixe_Annuel_MAD"] = salaire.round(2)
    df["Label"] = label
    # Les ratios, recalculés comme dans anomaly_pretraitement.py.
    df["CompaRatio"] = df.Fixe_Annuel_MAD / df.Mid
    df["RangePenetration"] = (df.Fixe_Annuel_MAD - df.Min) / (df.Max - df.Min)
    df["MarketRatio"] = df.Fixe_Annuel_MAD / df.Market_Median
    return df


def mesurer(df: pd.DataFrame, rule_params: dict, methode: str) -> dict:
    params = {**rule_params, "ml_methode": methode}
    d = former_cohortes(df, params)
    d = apply_rulebook(d, params)
    d = ml_anomaly(d, params)
    d = apply_ml_strong_signal(d, params)
    d = aggregate_risk(d, params)
    vrai = d.Label.isin(ANOMALIES).to_numpy()
    score = d.ML_AnomalyScore.to_numpy()
    top = score >= np.quantile(score, 0.95)
    signal = d.Rule_Flags.str.contains("ML_STRONG_SIGNAL", na=False).to_numpy()
    haut = d.Severity.isin(["Critical", "Major"]).to_numpy()
    return {
        "Précision moyenne IA": round(average_precision_score(vrai, score), 2),
        "Précision moyenne score général": round(average_precision_score(vrai, d.RiskScore), 2),
        "Top 5 % IA : vraies anomalies": int((top & vrai).sum()),
        "Top 5 % IA : dont subtiles": int((top & (d.Label == "subtil").to_numpy()).sum()),
        "Top 5 % IA : au-dessus du Max": int((top & (d.Label == "au_dessus").to_numpy()).sum()),
        "Signal fort : salariés": int(signal.sum()),
        "Signal fort : vraies anomalies": int((signal & vrai).sum()),
        "Critical + Major : salariés": int(haut.sum()),
        "Critical + Major : vraies anomalies": int((haut & vrai).sum()),
        "Anomalies à trouver": int(vrai.sum()),
        "Dont subtiles": int((d.Label == "subtil").sum()),
    }


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    with open(PROJET / "config" / "rules.yaml", encoding="utf-8") as fichier:
        rule_params = yaml.safe_load(fichier)["rules"]
    actuel = preparer_employes(PROJET / "input" / "employes.xlsx", PROJET / "input" / "bands.xlsx",
                               PROJET / "input" / "market.xlsx")
    actuel["Label"] = np.where(actuel.Fixe_Annuel_MAD < actuel.Min, "sous_min",
                               np.where(actuel.Fixe_Annuel_MAD > actuel.Max, "au_dessus", "normal"))
    jeux = {"Fichiers actuels": actuel, "Données réalistes": donnees_realistes(actuel)}
    resultats = {}
    for nom_jeu, df in jeux.items():
        for methode, nom in [("isolation_forest", "Isolation Forest"), ("ecart_attendu", "Écart à l'attendu")]:
            print(f"{nom_jeu} - {nom}...", flush=True)
            resultats[(nom_jeu, nom)] = mesurer(df, rule_params, methode)
    tableau = pd.DataFrame(resultats)
    print()
    print(tableau.to_string())
    sortie = PROJET / "output" / "analyse_modeles" / "banc_essai_ia.xlsx"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    tableau.to_excel(sortie)
    print(f"\nRésultats enregistrés dans : {sortie}")
