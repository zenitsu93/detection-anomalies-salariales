# -*- coding: utf-8 -*-
"""
Tests de apply_ml_strong_signal() : cette fonction rattrape un cas precis, ajoute suite au rapport
de test (voir rapport.md et corrections.txt) : un salarie peut etre en parfaite conformite avec
les regles simples (dans sa fourchette, CompaRatio correct...) mais avoir un profil tres atypique
detecte par l'intelligence artificielle (ex: age/anciennete incoherents avec son grade). Sans
cette fonction, ce genre de cas restait invisible car les regles simples pesent 70% du score final
par defaut, contre 30% pour l'IA : un tres bon score IA seul (30% de 100) ne suffit jamais a
depasser le seuil "Info".

Cette fonction fait remonter le score de risque pour ces cas precis, mais UNIQUEMENT si :
- aucune regle simple ne s'est deja declenchee pour ce salarie (sinon il est deja detecte), et
- il y a assez de salaries dans le fichier pour que "un score tres eleve" ait un sens statistique.
"""

import pandas as pd

from anomaly_core import apply_ml_strong_signal


def jeu_de_donnees(nb_lignes_normales):
    """Construit un petit jeu de test : des salaries "normaux" (score IA bas), un salarie au
    profil tres atypique et sans aucune regle declenchee, et un salarie au score tout aussi
    atypique mais qui a deja ete repere par une regle simple."""
    lignes_normales = pd.DataFrame({
        "ML_AnomalyScore": [10.0] * nb_lignes_normales,
        "Rule_Flags": [""] * nb_lignes_normales,
        "Rule_Score": [0.0] * nb_lignes_normales,
        "Reason_Principale": [""] * nb_lignes_normales,
    })
    lignes_particulieres = pd.DataFrame({
        "ML_AnomalyScore": [95.0, 95.0],
        "Rule_Flags": ["", "COMPA_RATIO"],
        "Rule_Score": [0.0, 20.0],
        "Reason_Principale": ["", "CompaRatio=1.40 (>1.15)"],
    })
    return pd.concat([lignes_normales, lignes_particulieres], ignore_index=True)


def test_profil_atypique_sans_aucune_regle_declenchee_est_remonte():
    """Le salarie au score IA tres eleve (95) et sans aucune regle declenchee doit recevoir
    l'etiquette ML_STRONG_SIGNAL, un bonus de score (15 points par defaut), et une phrase
    d'explication dediee."""
    df = jeu_de_donnees(nb_lignes_normales=23)  # 25 lignes au total : assez pour etre significatif
    resultat = apply_ml_strong_signal(df, rule_params={})
    ligne_sans_regle = resultat.iloc[23]
    assert "ML_STRONG_SIGNAL" in ligne_sans_regle["Rule_Flags"]
    assert ligne_sans_regle["Rule_Score"] == 15
    assert "atypique" in ligne_sans_regle["Reason_Principale"].lower()


def test_profil_atypique_deja_repere_par_une_regle_n_est_pas_compte_deux_fois():
    """Le salarie au meme score IA tres eleve (95), mais deja repere par une regle simple
    (COMPA_RATIO), ne doit PAS recevoir en plus le bonus ML_STRONG_SIGNAL : il est deja detecte,
    inutile de faire remonter un deuxieme signal pour la meme personne."""
    df = jeu_de_donnees(nb_lignes_normales=23)
    resultat = apply_ml_strong_signal(df, rule_params={})
    ligne_deja_reperee = resultat.iloc[24]
    assert "ML_STRONG_SIGNAL" not in ligne_deja_reperee["Rule_Flags"]
    assert ligne_deja_reperee["Rule_Score"] == 20  # score inchange (celui de COMPA_RATIO uniquement)


def test_salaries_normaux_ne_sont_jamais_signales():
    """Les salaries avec un score IA bas ne doivent jamais recevoir ML_STRONG_SIGNAL, quel que
    soit leur nombre."""
    df = jeu_de_donnees(nb_lignes_normales=23)
    resultat = apply_ml_strong_signal(df, rule_params={})
    lignes_normales = resultat.iloc[:23]
    assert (~lignes_normales["Rule_Flags"].str.contains("ML_STRONG_SIGNAL")).all()


def test_trop_peu_de_salaries_dans_le_fichier_desactive_la_regle():
    """Avec moins de 20 salaries au total, un score eleve n'a pas assez de sens statistique (le
    calcul de percentile ne serait pas fiable) : la fonction doit alors ne rien changer du tout,
    meme pour un salarie au score tres eleve et sans regle declenchee."""
    df = jeu_de_donnees(nb_lignes_normales=10)  # 12 lignes au total : sous le seuil de 20
    resultat = apply_ml_strong_signal(df, rule_params={})
    pd.testing.assert_frame_equal(resultat, df)


def test_percentile_personnalise_change_le_nombre_de_cas_signales():
    """Si le rulebook demande un seuil (percentile) plus bas que le defaut de 0.95, davantage de
    salaries doivent pouvoir etre signales : ce reglage doit bien etre lu depuis rule_params."""
    df = jeu_de_donnees(nb_lignes_normales=23)
    resultat_seuil_bas = apply_ml_strong_signal(df.copy(), rule_params={"ml_strong_signal_percentile": 0.5})
    resultat_seuil_defaut = apply_ml_strong_signal(df.copy(), rule_params={})
    nb_signales_seuil_bas = resultat_seuil_bas["Rule_Flags"].str.contains("ML_STRONG_SIGNAL").sum()
    nb_signales_seuil_defaut = resultat_seuil_defaut["Rule_Flags"].str.contains("ML_STRONG_SIGNAL").sum()
    assert nb_signales_seuil_bas > nb_signales_seuil_defaut
