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


def test_recommandations_suivent_les_seuils_configures():
    df = pd.DataFrame({"Fixe_Annuel_MAD": [88., 112.], "Min": [70., 70.],
                       "Mid": [100., 100.], "Max": [140., 140.], "CompaRatio": [.88, 1.12]})
    result = recommendations(df, {"compa_ratio_low": .9, "compa_ratio_high": 1.1})
    assert result.Reco.tolist() == ["Ajuster vers MID", "Compa élevée: Revue"]
    assert result.Cout_Ajustement.tolist() == [12., 0.]


@pytest.mark.parametrize("salary", [0., -100., np.inf])
def test_regression_exclut_un_salaire_inexploitable_sans_perdre_les_autres(salary):
    df = jeu_de_donnees()
    df.loc[0, "Fixe_Annuel_MAD"] = salary
    result, model = regression_anomaly(df, {})
    assert model is not None
    assert pd.isna(result.loc[0, "Reg_AnomalyScore"])
    assert np.isfinite(result.loc[1:, "Reg_AnomalyScore"]).all()
    assert model.nobs == len(df) - 1


def test_rapport_hf_ne_compare_pas_hommes_et_categorie_autre():
    df = jeu_de_donnees()
    df["Sexe"] = "M"
    df.loc[:4, "Sexe"] = "F"
    _, model = regression_anomaly(df, {})
    assert model is not None
    assert regression_gender_gap_report(model, {})["available"] is False


def test_rapport_hf_selectionne_m_meme_si_une_autre_modalite_existe():
    df = jeu_de_donnees(n=400, coef_sexe_log=np.log(1.1))
    df.loc[:29, "Sexe"] = "Autre"
    _, model = regression_anomaly(df, {})
    report = regression_gender_gap_report(model, {})
    expected = model.params['C(Sexe, Treatment(reference="F"))[T.M]']
    assert report["available"] is True
    assert report["coef_log"] == pytest.approx(expected)


def test_tableau_affiche_les_libelles_comme_du_texte():
    result = table_html([{"Metier": "<Audit & Risques>"}])
    assert "&lt;Audit &amp; Risques&gt;" in result
    assert "<Audit" not in result


def test_dashboard_ne_change_pas_unite_et_protege_les_donnees_embarquees():
    label = '</script><script>alert(1)</script>'
    df = pd.DataFrame({"Matricule": ["1"], "Entite_N1": [label], "Job_Family": ["IT"],
                       "Severity": ["Minor"], "RiskScore": [35.],
                       "Cout_Ajustement": [1500.], "Rule_Flags": ["COMPA_RATIO"]})
    data = build_data(df, pd.DataFrame())
    result = build_html(data)
    assert data["kpis"]["total_cost"] == 1500.
    assert "K MAD" not in result
    assert label not in result


def test_dashboard_est_une_page_complete_en_francais():
    # Pourquoi : sans doctype ni charset, les accents pouvaient mal s'afficher ; sans fusion
    # profonde, la légende « undefined » réapparaissait ; sans locale, les nombres étaient en anglais.
    df = pd.DataFrame({"Matricule": ["1"], "Entite_N1": ["Pole 1"], "Job_Family": ["IT"],
                       "Severity": ["Minor"], "RiskScore": [35.],
                       "Cout_Ajustement": [1500.], "Rule_Flags": ["COMPA_RATIO"]})
    result = build_html(build_data(df, pd.DataFrame()))
    assert result.startswith("<!doctype html>")
    assert '<html lang="fr">' in result and '<meta charset="utf-8">' in result
    assert "Object.assign(opts, extra)" not in result and "function merge(" in result
    assert "locale: 'fr-FR'" in result


def test_dashboard_aligne_les_tranches_du_score_sur_les_seuils_de_severite():
    # Pourquoi : la sévérité vaut « score >= seuil bas » ; avec des tranches fermées à droite,
    # un score de 30 (Mineure) tombait dans la tranche 20-30, colorée comme les Info.
    df = pd.DataFrame({"Matricule": list("abcd"), "Entite_N1": ["P1"] * 4, "Job_Family": ["IT"] * 4,
                       "Severity": ["Info", "Minor", "Major", "Critical"], "RiskScore": [29.9, 30., 50., 70.],
                       "Cout_Ajustement": [0.] * 4, "Rule_Flags": ["", "COMPA_RATIO", "MARKET_GAP", "OUT_OF_BAND"]})
    data = build_data(df, pd.DataFrame())
    dist = {row["Tranche_RiskScore"]: row for row in data["tables"]["riskscore_dist"]}
    assert (dist["20-30"]["Count"], dist["20-30"]["Severity"]) == (1, "Info")
    assert (dist["30-40"]["Count"], dist["30-40"]["Severity"]) == (1, "Minor")
    assert (dist["70-80"]["Count"], dist["70-80"]["Severity"]) == (1, "Critical")
    assert "Position dans la grille" in data["flags"]["labels"] and "COMPA_RATIO" in data["flags"]["codes"]
    # Les Info (aucune action) ne sont plus empilées avec les anomalies à traiter.
    assert [d["code"] for d in data["severity"]["datasets"]] == ["Critical", "Major", "Minor"]


def test_excel_conserve_les_nombres_les_totaux_et_l_ordre_des_priorites(tmp_path):
    from openpyxl import load_workbook

    df = pd.DataFrame({"Matricule": ["a", "b", "c", "d"],
                       "Severity": ["Info", "Minor", "Major", "Critical"],
                       "RiskScore": [10., 35., 55., 75.],
                       "Cout_Ajustement": [1234.56, 100., 0., 5.],
                       "Entite_N1": ["IT"] * 4})
    path = tmp_path / "resultat.xlsx"
    to_excel_colored(df, path)
    wb = load_workbook(path)
    rows = list(wb["All"].values)
    assert [r[1] for r in rows[1:]] == ["Critical", "Major", "Minor", "Info"]
    assert all(isinstance(r[3], (int, float)) for r in rows[1:])
    stats = dict(list(wb["Statistics"].values)[1:])
    assert stats["Total salariés analysés"] == 4
    assert stats["Total adjustment cost"] == pytest.approx(1339.56)
    assert list(wb["Budget_Synthese"].values)[-1][-1] == pytest.approx(1339.56)
    assert wb["Statistics"]._charts[0].series[0].val.numRef.f.endswith("$B$3:$B$6")
    wb.close()
