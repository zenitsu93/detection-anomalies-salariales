# -*- coding: utf-8 -*-
"""
Tests de apply_rulebook() : la fonction qui applique les regles simples et explicites (pas de
l'intelligence artificielle ici, juste des seuils configurables) :

- OUT_OF_BAND : le salaire sort de la fourchette interne (Min/Max), avec une petite tolerance.
- COMPA_RATIO : le salaire est trop loin du milieu de la fourchette (Mid).
- MARKET_GAP  : le salaire est trop loin de la mediane du marche externe.

Chaque regle declenchee ajoute une etiquette dans Rule_Flags, augmente Rule_Score du poids
correspondant, et vient enrichir la phrase d'explication Reason_Principale.
"""

import pandas as pd
import pytest

from anomaly_core import apply_rulebook


def ligne(compa_ratio, range_penetration, market_ratio=None):
    return pd.DataFrame({
        "CompaRatio": [compa_ratio],
        "RangePenetration": [range_penetration],
        "MarketRatio": [market_ratio],
    })


def test_salarie_parfaitement_dans_les_clous_ne_declenche_aucune_regle():
    """Un salarie dont le salaire est bien dans sa fourchette, avec un CompaRatio et un
    MarketRatio raisonnables, ne doit recevoir aucune etiquette, un score de 0, et une explication
    vide : l'outil ne doit jamais "inventer" une anomalie qui n'existe pas."""
    df = ligne(compa_ratio=1.0, range_penetration=0.5, market_ratio=1.0)
    resultat = apply_rulebook(df, rule_params={})
    assert resultat.loc[0, "Rule_Flags"] == ""
    assert resultat.loc[0, "Rule_Score"] == 0
    assert resultat.loc[0, "Reason_Principale"] == ""


def test_salaire_sous_le_minimum_declenche_out_of_band():
    """Un salaire nettement sous le Min de la fourchette (RangePenetration negatif, au-dela de la
    tolerance par defaut de -0.05) doit declencher OUT_OF_BAND et ajouter 30 points au score par
    defaut."""
    df = ligne(compa_ratio=1.0, range_penetration=-0.20, market_ratio=1.0)
    resultat = apply_rulebook(df, rule_params={})
    assert "OUT_OF_BAND" in resultat.loc[0, "Rule_Flags"]
    assert resultat.loc[0, "Rule_Score"] == 30
    assert "MIN" in resultat.loc[0, "Reason_Principale"]


def test_salaire_au_dessus_du_maximum_declenche_out_of_band():
    """Symetrique du test precedent : un salaire nettement au-dessus du Max doit aussi declencher
    OUT_OF_BAND, avec une explication qui parle du MAX (et non du MIN)."""
    df = ligne(compa_ratio=1.0, range_penetration=1.20, market_ratio=1.0)
    resultat = apply_rulebook(df, rule_params={})
    assert "OUT_OF_BAND" in resultat.loc[0, "Rule_Flags"]
    assert "MAX" in resultat.loc[0, "Reason_Principale"]


def test_compa_ratio_trop_bas_ou_trop_haut_declenche_compa_ratio():
    """Un CompaRatio en dehors de [0.85, 1.15] (par defaut) doit declencher COMPA_RATIO et ajouter
    20 points, que ce soit trop bas ou trop haut."""
    trop_bas = apply_rulebook(ligne(compa_ratio=0.70, range_penetration=0.5), rule_params={})
    trop_haut = apply_rulebook(ligne(compa_ratio=1.40, range_penetration=0.5), rule_params={})
    assert "COMPA_RATIO" in trop_bas.loc[0, "Rule_Flags"]
    assert trop_bas.loc[0, "Rule_Score"] == 20
    assert "COMPA_RATIO" in trop_haut.loc[0, "Rule_Flags"]


def test_ecart_marche_declenche_market_gap_seulement_si_la_donnee_marche_existe():
    """Un MarketRatio hors de [0.90, 1.20] doit declencher MARKET_GAP (+15 points) ; mais si aucun
    marche n'est disponible pour ce salarie (MarketRatio manquant, NaN), aucune regle marche ne
    doit se declencher (on ne peut pas comparer a une donnee qu'on n'a pas)."""
    avec_ecart = apply_rulebook(ligne(compa_ratio=1.0, range_penetration=0.5, market_ratio=0.5), rule_params={})
    assert "MARKET_GAP" in avec_ecart.loc[0, "Rule_Flags"]
    assert avec_ecart.loc[0, "Rule_Score"] == 15

    sans_marche = apply_rulebook(ligne(compa_ratio=1.0, range_penetration=0.5, market_ratio=None), rule_params={})
    assert "MARKET_GAP" not in sans_marche.loc[0, "Rule_Flags"]
    assert sans_marche.loc[0, "Rule_Score"] == 0


def test_plusieurs_regles_declenchees_en_meme_temps_s_additionnent():
    """Un salarie qui cumule plusieurs problemes (hors bande ET compa ratio anormal) doit voir les
    deux etiquettes apparaitre, les deux poids s'additionner dans le score, et les deux
    explications apparaitre dans Reason_Principale (separees par ' & ')."""
    df = ligne(compa_ratio=1.50, range_penetration=1.30, market_ratio=1.0)
    resultat = apply_rulebook(df, rule_params={})
    assert "OUT_OF_BAND" in resultat.loc[0, "Rule_Flags"]
    assert "COMPA_RATIO" in resultat.loc[0, "Rule_Flags"]
    assert resultat.loc[0, "Rule_Score"] == 30 + 20
    assert " & " in resultat.loc[0, "Reason_Principale"]


def test_les_seuils_et_poids_du_rulebook_sont_bien_pris_en_compte():
    """Si le rulebook (le fichier de reglages) definit des seuils et des poids differents des
    valeurs par defaut, ce sont ces valeurs personnalisees qui doivent etre utilisees, pas les
    valeurs par defaut codees dans le programme."""
    rule_params = {
        "compa_ratio_low": 0.95,
        "compa_ratio_high": 1.05,
        "severity_weights": {"compa_ratio": 99},
    }
    # 0.90 est hors de la fourchette personnalisee [0.95, 1.05] mais serait accepte par defaut [0.85, 1.15]
    df = ligne(compa_ratio=0.90, range_penetration=0.5, market_ratio=1.0)
    resultat = apply_rulebook(df, rule_params=rule_params)
    assert "COMPA_RATIO" in resultat.loc[0, "Rule_Flags"]
    assert resultat.loc[0, "Rule_Score"] == 99
