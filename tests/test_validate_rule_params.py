# -*- coding: utf-8 -*-
"""
Tests de validate_rule_params() : la fonction qui verifie, au demarrage, que le fichier de
reglages (rulebook) fourni par l'utilisateur contient bien tout ce que le programme attend. Si une
cle manque, un message d'avertissement doit apparaitre, mais le programme doit continuer a
fonctionner avec une valeur par defaut (comportement volontairement non bloquant).
"""

import copy

from anomaly_core import EXPECTED_RULE_KEYS, validate_rule_params


def rulebook_complet():
    """Une copie independante de la structure attendue : sert a simuler un rulebook qui contient
    absolument tout ce que le programme s'attend a trouver."""
    return copy.deepcopy(EXPECTED_RULE_KEYS)


def test_rulebook_vide_declenche_un_avertissement_par_cle_manquante(capsys):
    """Avec un rulebook completement vide, chaque reglage attendu doit declencher son propre
    avertissement, pour que l'utilisateur sache precisement ce qui manque plutot que de decouvrir
    un comportement par defaut au hasard."""
    validate_rule_params({})
    message_erreurs = capsys.readouterr().err
    for cle in EXPECTED_RULE_KEYS:
        assert f"rules.{cle}" in message_erreurs


def test_rulebook_complet_ne_declenche_aucun_avertissement(capsys):
    """A l'inverse, si le rulebook contient deja tout ce qui est attendu (memes cles, y compris
    les sous-reglages de severity_weights et de prioritization_buckets), aucun avertissement ne
    doit apparaitre : l'outil ne doit pas se plaindre d'un fichier pourtant correct."""
    validate_rule_params(rulebook_complet())
    message_erreurs = capsys.readouterr().err
    assert message_erreurs == ""


def test_un_seul_sous_reglage_manquant_dans_severity_weights_est_signale_precisement(capsys):
    """Si seul un des poids (ici "peer_outlier") manque a l'interieur de severity_weights, c'est
    precisement ce sous-reglage qui doit etre signale - pas l'ensemble de severity_weights, qui
    est par ailleurs bien present."""
    rulebook = rulebook_complet()
    del rulebook["severity_weights"]["peer_outlier"]
    validate_rule_params(rulebook)
    message_erreurs = capsys.readouterr().err
    assert "rules.severity_weights.peer_outlier" in message_erreurs
    assert "rules.severity_weights'" not in message_erreurs  # le bloc entier n'est pas signale comme absent


def test_un_reglage_simple_manquant_est_signale_avec_sa_valeur_par_defaut(capsys):
    """Si un reglage simple (ici compa_ratio_low) est absent, le message doit mentionner a la fois
    le nom du reglage manquant et la valeur par defaut qui sera utilisee a la place, pour que
    l'utilisateur comprenne immediatement les consequences sans avoir a lire le code."""
    rulebook = rulebook_complet()
    del rulebook["compa_ratio_low"]
    validate_rule_params(rulebook)
    message_erreurs = capsys.readouterr().err
    assert "rules.compa_ratio_low" in message_erreurs
    assert str(EXPECTED_RULE_KEYS["compa_ratio_low"]) in message_erreurs
