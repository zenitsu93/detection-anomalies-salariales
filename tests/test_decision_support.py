"""Vérification des simulations, de leurs limites et de l'API locale."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from decision_support.engine import DecisionEngine
from decision_support.app import make_handler


def references():
    employees = pd.DataFrame({"Matricule": [f"M{i}" for i in range(6)],
                              "Job_Family": ["IT"] * 6, "Grade": ["2"] * 6,
                              "Anciennete": [3.] * 6, "Fixe_Annuel_MAD": [90., 95., 100., 105., 110., 115.]})
    bands = pd.DataFrame({"Job_Family": ["IT", "RH"], "Grade": ["2", "2"],
                         "Min": [70., 140.], "Mid": [100., 200.], "Max": [140., 280.]})
    market = pd.DataFrame({"Job_Family": ["IT", "RH"], "Grade": ["2", "2"], "Median": [100., 200.]})
    return employees, bands, market


def engine(**kwargs):
    return DecisionEngine(*references(), rules={}, **kwargs)


def profile(**kwargs):
    return {"mode": "evaluate", "job_family": "IT", "grade": "2", "seniority": 3, "salary": 100., **kwargs}


def test_evaluation_coherente_explique_les_quatre_comparaisons():
    result = engine().analyze(profile())
    assert result["status"] == "coherent"
    assert len(result["checks"]) == 4
    assert all(c["status"] == "ok" for c in result["checks"])
    assert result["checks"][1]["value"] == 1.


def test_salaire_hors_bande_est_signale_meme_dans_l_ancienne_marge():
    result = engine().analyze(profile(salary=69))
    assert result["status"] == "review"
    assert result["checks"][0]["status"] == "review"


def test_proposition_intersection_et_mediane_sans_salaire_fourni():
    result = engine().analyze(profile(mode="propose", salary=None))
    assert result["proposal"]["low"] == 96.25
    assert result["proposal"]["high"] == 108.75
    assert result["proposal"]["target"] == 102.5
    assert result["salary"] is None
    assert result["checks"] == []


def test_grille_depend_du_metier_et_du_grade_sans_melange():
    result = engine().analyze(profile(mode="propose", job_family="RH"))
    assert result["band"]["Mid"] == 200
    assert result["peers"]["count"] == 0
    assert result["proposal"]["target"] == 200
    assert result["status"] == "insufficient"


def test_anciennete_elargit_uniquement_au_meme_metier_et_grade():
    result = engine().analyze(profile(seniority=25))
    assert result["peers"]["count"] == 6
    assert result["peers"]["scope"] == "Même métier et même grade"
    assert any("élargie" in w for w in result["warnings"])


def test_salarie_exclu_de_sa_propre_comparaison():
    result = engine().analyze(profile(employee_id="M5"))
    assert result["peers"]["count"] == 5
    assert result["peers"]["median"] == 100.


def test_simulation_n_influence_pas_les_references_et_ne_modifie_pas_les_sources():
    emp, band, market = references()
    before = emp.copy(deep=True)
    calc = DecisionEngine(emp, band, market, {})
    first = calc.analyze(profile(salary=100))
    second = calc.analyze(profile(salary=100000))
    assert first["peers"] == second["peers"]
    assert first["proposal"] == second["proposal"]
    pd.testing.assert_frame_equal(emp, before)


def test_age_sexe_et_competences_non_calibrees_ne_changent_pas_la_proposition():
    calc = engine()
    first = calc.analyze(profile(mode="propose", age=25, sexe="F", competence=1))
    second = calc.analyze(profile(mode="propose", age=60, sexe="M", competence=5))
    assert first == second


def test_sans_grille_pas_de_proposition_inventee():
    result = engine().analyze(profile(mode="propose", grade="999"))
    assert result["proposal"]["target"] is None
    assert result["status"] == "insufficient"


def test_marche_absent_autorise_un_repere_interne_explicitement_partiel():
    emp, band, _ = references()
    result = DecisionEngine(emp, band, None, {}).analyze(profile(mode="propose"))
    assert result["market"] is None
    assert result["proposal"]["target"] == 102.5
    assert result["status"] == "insufficient"


def test_grilles_contradictoires_ne_sont_pas_resolues_en_prenant_la_premiere():
    emp, bands, market = references()
    duplicate = bands.iloc[[0]].copy(); duplicate["Mid"] = 110.
    result = DecisionEngine(emp, pd.concat([bands, duplicate]), market, {}).analyze(profile(mode="propose"))
    assert result["band"] is None
    assert any("contradictoires" in w for w in result["warnings"])


def test_references_incompatibles_ne_donnent_pas_une_fausse_fourchette():
    emp, bands, market = references()
    market.loc[0, "Median"] = 1000.
    result = DecisionEngine(emp, bands, market, {}).analyze(profile(mode="propose"))
    assert result["proposal"]["reason"] == "conflict"
    assert result["proposal"]["target"] is None
    assert result["status"] == "review"


def test_pairs_identiques_ne_masquent_pas_un_ecart():
    emp, bands, market = references(); emp["Fixe_Annuel_MAD"] = 100.
    result = DecisionEngine(emp, bands, market, {}).analyze(profile(salary=101))
    assert result["checks"][-1]["status"] == "review"
    json.dumps(result, allow_nan=False)


def test_proposition_ne_declenche_pas_sa_propre_alerte_aux_bornes():
    emp, band, market = references()
    emp["Fixe_Annuel_MAD"] = [260., 270., 280., 290., 330., 340.]
    band.loc[0, ["Min", "Mid", "Max"]] = [200., 338., 450.]
    market.loc[0, "Median"] = 338.
    calc = DecisionEngine(emp, band, market, {})
    proposal = calc.analyze(profile(mode="propose"))["proposal"]
    assert proposal["target"] == 304.2
    assert calc.analyze(profile(salary=proposal["target"]))["status"] == "coherent"


def test_quartiles_ne_suffisent_pas_si_la_cible_declencherait_une_alerte_pairs():
    emp, band, market = references()
    emp["Fixe_Annuel_MAD"] = [80., 90., 122., 123., 124., 125.]
    result = DecisionEngine(emp, band, market, {}).analyze(profile(mode="propose"))
    assert result["proposal"]["reason"] == "conflict"
    assert result["proposal"]["target"] is None


@pytest.mark.parametrize("changes", [{"salary": 0}, {"salary": -1}, {"salary": np.inf},
                                    {"salary": "texte"}, {"seniority": -1}, {"mode": "unknown"},
                                    {"job_family": ""}, {"employee_id": "inconnu"}])
def test_saisie_invalide_rejetee(changes):
    with pytest.raises(ValueError):
        engine().analyze(profile(**changes))


def test_seuils_communs_du_rulebook_utilises():
    emp, bands, market = references()
    result = DecisionEngine(emp, bands, market, {"compa_ratio_low": .99}).analyze(profile(salary=98))
    assert result["checks"][1]["status"] == "review"
    assert result["proposal"]["low"] == 99.


def test_doublons_de_matricule_exclus_sans_modifier_le_fichier():
    emp, bands, market = references(); emp.loc[1, "Matricule"] = "M0"
    result = DecisionEngine(emp, bands, market, {}).analyze(profile())
    assert result["peers"]["count"] == 4
    assert result["peers"]["available"] is False
    assert any("dupliqué" in w for w in result["warnings"])


def test_api_locale_modes_validation_et_pages():
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(engine()))
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        for path in ["/", "/app.js", "/style.css", "/api/metadata"]:
            connection.request("GET", path); response = connection.getresponse()
            assert response.status == 200; response.read()
        for mode in ["evaluate", "propose"]:
            connection.request("POST", "/api/analyze", json.dumps(profile(mode=mode)), {"Content-Type": "application/json"})
            response = connection.getresponse(); result = json.loads(response.read())
            assert response.status == 200
            assert result["mode"] == mode
        connection.request("POST", "/api/analyze", json.dumps(profile(salary=-10)), {"Content-Type": "application/json"})
        response = connection.getresponse(); response.read(); assert response.status == 400
        connection.request("GET", "/api/metadata", headers={"Origin": "https://example.com"})
        response = connection.getresponse(); response.read(); assert response.status == 403
    finally:
        connection.close(); server.shutdown(); server.server_close(); thread.join(timeout=5)
