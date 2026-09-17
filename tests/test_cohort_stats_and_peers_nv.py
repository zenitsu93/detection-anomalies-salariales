# -*- coding: utf-8 -*-
"""
Tests de cohort_stats_and_peers_nv() : la fonction qui construit les groupes de comparaison
("cohortes") et repere les salaries qui se demarquent nettement de leurs collegues directs (meme
grade, meme metier, anciennete comparable).

Deux idees a retenir :
1. Un groupe de comparaison trop petit n'est pas fiable statistiquement (comparer un salarie a 2
   collegues n'a pas beaucoup de sens) : la fonction elargit alors automatiquement le groupe,
   mais UNIQUEMENT pour les groupes trop petits, pas pour tout le monde.
2. A l'interieur de chaque groupe, un salarie dont le salaire s'ecarte nettement de ses collegues
   recoit une etiquette PEER_OUTLIER, et un impact sur le score si l'ecart est vraiment important.

Cette fonction attend un tableau qui a deja ete traite par apply_rulebook() (elle lit et complete
les colonnes Rule_Flags/Rule_Score/Reason_Principale) : les jeux de test ci-dessous les incluent
donc des le depart, avec des valeurs neutres.
"""

import pandas as pd
import pytest

from anomaly_core import cohort_stats_and_peers_nv


def salaries_neutres(n, **colonnes):
    """Construit un petit tableau de salaries avec les colonnes obligatoires deja presentes et
    neutres (aucune regle simple pre-declenchee), pour ne tester que l'effet des cohortes."""
    base = {
        "Matricule": list(range(1, n + 1)),
        "Rule_Flags": [""] * n,
        "Rule_Score": [0.0] * n,
        "Reason_Principale": [""] * n,
    }
    base.update(colonnes)
    return pd.DataFrame(base)


def test_groupe_assez_grand_n_est_pas_elargi():
    """Avec 6 salaries dans un meme groupe (grade + metier + anciennete), au-dessus du minimum par
    defaut de 5, la cohorte ne doit pas etre elargie : la cle de cohorte doit rester la
    combinaison complete grade/metier/anciennete, pour une comparaison la plus fine possible."""
    df = salaries_neutres(
        6,
        Grade=["G1"] * 6,
        Job_Family=["IT"] * 6,
        Anciennete_Bucket=["0-2"] * 6,
        Fixe_Annuel_MAD=[100, 101, 99, 100, 102, 98],
    )
    resultat = cohort_stats_and_peers_nv(df, rule_params={})
    assert (resultat["Cohort_Key"] == "G1|IT|0-2").all()
    assert (resultat["Cohort_Size"] == 6).all()


def test_deux_petits_groupes_sont_fusionnes_uniquement_entre_eux():
    """Deux groupes de 3 personnes (sous le minimum de 5), avec le meme grade et le meme metier
    mais une anciennete differente, doivent etre fusionnes ensemble (grade+metier, sans
    l'anciennete) pour atteindre une taille suffisante. Un troisieme groupe, deja assez grand et
    sans lien de grade/metier avec les deux premiers, ne doit lui surtout pas etre touche : c'est
    la preuve que l'elargissement est cible, pas applique a l'aveugle a tout le fichier."""
    petit_groupe_a = salaries_neutres(
        3, Grade=["G1"] * 3, Job_Family=["IT"] * 3, Anciennete_Bucket=["0-2"] * 3,
        Fixe_Annuel_MAD=[100, 101, 99],
    )
    petit_groupe_b = salaries_neutres(
        3, Grade=["G1"] * 3, Job_Family=["IT"] * 3, Anciennete_Bucket=["6-12"] * 3,
        Fixe_Annuel_MAD=[102, 98, 100],
    )
    petit_groupe_b["Matricule"] = [4, 5, 6]
    groupe_deja_suffisant = salaries_neutres(
        5, Grade=["G2"] * 5, Job_Family=["RH"] * 5, Anciennete_Bucket=["13-20"] * 5,
        Fixe_Annuel_MAD=[200, 201, 199, 200, 202],
    )
    groupe_deja_suffisant["Matricule"] = [7, 8, 9, 10, 11]

    df = pd.concat([petit_groupe_a, petit_groupe_b, groupe_deja_suffisant], ignore_index=True)
    resultat = cohort_stats_and_peers_nv(df, rule_params={})

    cles_ab = resultat.loc[resultat["Matricule"].isin([1, 2, 3, 4, 5, 6]), "Cohort_Key"]
    assert (cles_ab == "G1|IT").all()  # elargis a grade+metier, anciennete abandonnee
    assert (resultat.loc[resultat["Matricule"].isin([1, 2, 3, 4, 5, 6]), "Cohort_Size"] == 6).all()

    cle_c = resultat.loc[resultat["Matricule"] == 7, "Cohort_Key"].iloc[0]
    assert cle_c == "G2|RH|13-20"  # inchange : deja suffisamment grand des le depart
    assert (resultat.loc[resultat["Matricule"].isin([7, 8, 9, 10, 11]), "Cohort_Size"] == 5).all()


def test_salarie_qui_gagne_beaucoup_plus_que_ses_collegues_directs_est_repere():
    """Au sein d'un meme groupe de comparaison, un salarie dont le salaire s'ecarte nettement de
    ses collegues doit recevoir l'etiquette PEER_OUTLIER, et un bonus de score (15 points par
    defaut) car l'ecart est tres important (grand |PeerZ|)."""
    df = salaries_neutres(
        6,
        Grade=["G1"] * 6,
        Job_Family=["IT"] * 6,
        Anciennete_Bucket=["0-2"] * 6,
        Fixe_Annuel_MAD=[100, 101, 99, 100, 102, 400],  # le dernier gagne 4x plus que les autres
    )
    resultat = cohort_stats_and_peers_nv(df, rule_params={})
    ligne_outlier = resultat.iloc[5]
    assert "PEER_OUTLIER" in ligne_outlier["Rule_Flags"]
    assert ligne_outlier["Rule_Score"] == 15
    assert "pairs" in ligne_outlier["Reason_Principale"].lower()
    # les collegues, eux, ne doivent pas etre signales
    assert (~resultat.iloc[:5]["Rule_Flags"].str.contains("PEER_OUTLIER")).all()


def test_seuils_personnalises_du_rulebook_changent_la_detection():
    """Si le rulebook demande un seuil bien plus strict pour la detection entre pairs, un ecart
    qui aurait ete ignore par defaut doit desormais etre repere ; inversement, avec un seuil bien
    plus permissif, il ne doit plus l'etre. On verifie ainsi que les deux seuils (minor/major) sont
    bien lus depuis le rulebook plutot que fixes en dur."""
    df = salaries_neutres(
        6,
        Grade=["G1"] * 6,
        Job_Family=["IT"] * 6,
        Anciennete_Bucket=["0-2"] * 6,
        Fixe_Annuel_MAD=[100, 101, 99, 100, 102, 115],  # ecart modere, pas enorme
    )
    resultat_seuil_strict = cohort_stats_and_peers_nv(
        df.copy(), rule_params={"peer_z_threshold_minor": 0.1, "peer_z_threshold_major": 0.1}
    )
    resultat_seuil_permissif = cohort_stats_and_peers_nv(
        df.copy(), rule_params={"peer_z_threshold_minor": 50, "peer_z_threshold_major": 50}
    )
    assert "PEER_OUTLIER" in resultat_seuil_strict.iloc[5]["Rule_Flags"]
    assert "PEER_OUTLIER" not in resultat_seuil_permissif.iloc[5]["Rule_Flags"]


def test_statistiques_de_cohorte_correspondent_au_calcul_attendu():
    """Verifie que la mediane et la moyenne calculees pour une cohorte correspondent bien au
    calcul mathematique attendu sur des chiffres simples et verifiables a la main."""
    df = salaries_neutres(
        5,
        Grade=["G1"] * 5,
        Job_Family=["IT"] * 5,
        Anciennete_Bucket=["0-2"] * 5,
        Fixe_Annuel_MAD=[100, 110, 120, 130, 140],
    )
    resultat = cohort_stats_and_peers_nv(df, rule_params={})
    assert resultat["Cohort_Median"].iloc[0] == pytest.approx(120)
    assert resultat["Cohort_Mean"].iloc[0] == pytest.approx(120)
