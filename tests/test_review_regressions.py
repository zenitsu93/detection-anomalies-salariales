"""Cas limites découverts pendant la relecture du bilan de projet."""

import numpy as np
import pandas as pd
import pytest

from anomaly_core import (
    apply_ml_strong_signal, bucket_anciennete, ml_anomaly,
    recommendations, robust_zscore,
)
from anomaly_regression import regression_anomaly, regression_gender_gap_report
from anomaly_io import to_excel_colored
from generate_dashboard_html import build_data, build_html, table_html
from test_anomaly_regression import jeu_de_donnees


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf, -1])
def test_anciennete_absente_ou_invalide_ne_cree_pas_une_fausse_tranche(value):
    assert bucket_anciennete(value) == "NA"


def test_salaire_manquant_reste_sans_score_dans_un_groupe_constant():
    scores = robust_zscore(pd.Series([100, 100, np.nan]))
    assert scores.iloc[:2].eq(0).all()
    assert pd.isna(scores.iloc[2])


def test_scores_ia_identiques_ne_signalent_pas_toute_la_population():
    df = pd.DataFrame({"ML_AnomalyScore": [50.] * 25, "Rule_Flags": [""] * 25,
                       "Rule_Score": [0.] * 25, "Reason_Principale": [""] * 25})
    result = apply_ml_strong_signal(df.copy(), {})
    pd.testing.assert_frame_equal(result, df)


def test_ia_accepte_des_champs_rh_absents():
    result = ml_anomaly(pd.DataFrame({"Fixe_Annuel_MAD": np.arange(30) + 100}), {})
    assert result.ML_AnomalyScore.between(0, 100).all()


def test_ia_sans_donnee_exploitable_reste_indisponible(capsys):
    result = ml_anomaly(pd.DataFrame({"Fixe_Annuel_MAD": [np.nan] * 25}), {})
    assert result.ML_AnomalyScore.isna().all()
    assert "[WARN]" in capsys.readouterr().err

