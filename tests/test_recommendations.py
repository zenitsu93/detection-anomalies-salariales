# -*- coding: utf-8 -*-
"""
Tests de recommendations() : la fonction qui propose une action concrete pour chaque salarie
(rien, ajuster au minimum, ajuster vers le milieu de la fourchette, ou simplement revoir le
dossier) et estime le cout d'un eventuel ajustement salarial.

Ordre de priorite des cas (du plus urgent au moins urgent) : sous le Min > tres en dessous du
milieu de fourchette (Mid) > au-dessus du Max > CompaRatio trop eleve.
"""

import numpy as np
import pandas as pd
import pytest

from anomaly_core import recommendations


def salarie(fixe, mn, md, mx, compa):
    return pd.DataFrame({
        "Fixe_Annuel_MAD": [fixe], "Min": [mn], "Mid": [md], "Max": [mx], "CompaRatio": [compa],
    })


def test_salaire_sous_le_minimum_doit_etre_ajuste_au_minimum():
    """Un salaire sous le Min de la fourchette doit recevoir la recommandation "Ajuster au MIN",
    avec un cout d'ajustement egal exactement a la difference entre le Min et le salaire actuel."""
    df = salarie(fixe=80000, mn=90000, md=110000, mx=130000, compa=80000 / 110000)
    resultat = recommendations(df)
    assert resultat.loc[0, "Reco"] == "Ajuster au MIN"
    assert resultat.loc[0, "Cout_Ajustement"] == pytest.approx(10000)


def test_compa_ratio_bas_dans_la_fourchette_doit_etre_ajuste_vers_le_milieu():
    """Un salaire dans la fourchette (donc pas sous le Min) mais avec un CompaRatio bas (<0.85) et
    encore sous le Mid doit recevoir la recommandation "Ajuster vers MID", avec un cout egal a la
    difference entre le Mid et le salaire actuel."""
    df = salarie(fixe=92000, mn=90000, md=110000, mx=130000, compa=92000 / 110000)
    resultat = recommendations(df)
    assert resultat.loc[0, "Reco"] == "Ajuster vers MID"
    assert resultat.loc[0, "Cout_Ajustement"] == pytest.approx(18000)


def test_salaire_au_dessus_du_maximum_doit_etre_revu_sans_chiffrage():
    """Un salaire au-dessus du Max doit recevoir la recommandation "Au-dessus MAX: Revue", sans
    proposer de cout d'ajustement chiffre (une baisse de salaire n'est pas une recommandation
    automatique)."""
    df = salarie(fixe=140000, mn=90000, md=110000, mx=130000, compa=140000 / 110000)
    resultat = recommendations(df)
    assert resultat.loc[0, "Reco"] == "Au-dessus MAX: Revue"
    assert resultat.loc[0, "Cout_Ajustement"] == pytest.approx(0)


def test_compa_ratio_eleve_dans_la_fourchette_doit_etre_revu_sans_chiffrage():
    """Un salaire dans la fourchette mais avec un CompaRatio eleve (>1.15) doit recevoir la
    recommandation "Compa élevée: Revue", sans chiffrage automatique non plus."""
    df = salarie(fixe=128000, mn=90000, md=110000, mx=130000, compa=128000 / 110000)
    resultat = recommendations(df)
    assert resultat.loc[0, "Reco"] == "Compa élevée: Revue"
    assert resultat.loc[0, "Cout_Ajustement"] == pytest.approx(0)


def test_salaire_conforme_ne_recoit_aucune_recommandation():
    """Un salaire bien positionne (dans la fourchette, CompaRatio raisonnable) ne doit recevoir
    aucune recommandation et aucun cout : il n'y a rien a corriger."""
    df = salarie(fixe=110000, mn=90000, md=110000, mx=130000, compa=1.0)
    resultat = recommendations(df)
    assert resultat.loc[0, "Reco"] == ""
    assert resultat.loc[0, "Cout_Ajustement"] == pytest.approx(0)


def test_sans_fourchette_de_reference_aucune_recommandation_n_est_possible():
    """Si la fourchette interne (Min/Mid/Max) est manquante pour un salarie (grade sans
    correspondance, par exemple), aucune recommandation ne doit etre proposee : on ne peut pas
    recommander un ajustement sans reference fiable, et il ne faut surtout pas planter."""
    df = salarie(fixe=100000, mn=np.nan, md=np.nan, mx=np.nan, compa=np.nan)
    resultat = recommendations(df)
    assert resultat.loc[0, "Reco"] == ""
    assert resultat.loc[0, "Cout_Ajustement"] == pytest.approx(0)


def test_sous_le_minimum_est_prioritaire_meme_si_le_compa_ratio_est_aussi_bas():
    """Un salarie a la fois sous le Min ET avec un CompaRatio bas doit recevoir en priorite
    "Ajuster au MIN" (le cas le plus urgent), et non "Ajuster vers MID" : l'ordre de priorite doit
    etre respecte, pas seulement chaque condition prise isolement."""
    df = salarie(fixe=70000, mn=90000, md=110000, mx=130000, compa=70000 / 110000)
    resultat = recommendations(df)
    assert resultat.loc[0, "Reco"] == "Ajuster au MIN"
    assert resultat.loc[0, "Cout_Ajustement"] == pytest.approx(20000)
