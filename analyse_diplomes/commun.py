#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LES OUTILS DE LA PAGE DU DIPLÔME
===============================

Ce que diplome.py utilise sans que ce soit propre au diplôme : lire les fichiers, lancer la détection,
écrire les nombres à la française et écrire la page. Ce fichier ne se lance pas seul.

La page ne change pas la détection : elle la lance avec ses réglages habituels, puis avec le diplôme en
plus, et montre la différence. Les résultats de python src/detect_salary_anomalies.py restent les mêmes.
"""

import json
import sys
from urllib.parse import quote
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

# Le dossier du projet : un cran au-dessus de ce dossier (analyse_diplomes/).
PROJET = Path(__file__).resolve().parent.parent
# Pourquoi : les fichiers de src/ s'importent entre eux par leur seul nom (« from anomaly_pretraitement
# import ... ») ; Python doit donc aussi chercher dans ce dossier.
sys.path.insert(0, str(PROJET / "src"))

from anomaly_pretraitement import message_diplomes, preparer_employes  # noqa: E402
from anomaly_cohortes import former_cohortes  # noqa: E402
from anomaly_regles import apply_rulebook  # noqa: E402
from anomaly_signal_iforest import ml_anomaly  # noqa: E402
from anomaly_signal_fort import apply_ml_strong_signal  # noqa: E402
from anomaly_score_general import aggregate_risk  # noqa: E402
from generate_dashboard_html import VENDOR  # noqa: E402

# Les tranches de diplôme dans l'ordre (voir tranche_etude dans src/anomaly_pretraitement.py), plus les
# diplômes inconnus, toujours mis à part.
TRANCHES = ["BAC+2 ou moins", "BAC+3 ou BAC+4", "BAC+5 et plus"]
INCONNU = "Inconnu"


def charger():
    """Les réglages (config/rules.yaml) et les salariés prétraités, avec leur diplôme. S'arrête avec un
    message si aucun salarié n'a de diplôme connu : il n'y aurait rien à comparer."""
    with open(PROJET / "config" / "rules.yaml", encoding="utf-8") as fichier:
        rule_params = yaml.safe_load(fichier)["rules"]
    df = preparer_employes(PROJET / "input" / "employes.xlsx", PROJET / "input" / "bands.xlsx",
                           PROJET / "input" / "market.xlsx")
    print(message_diplomes(df))
    if df["Tranche_Etude"].notna().sum() == 0:
        raise SystemExit("Aucun salarié n'a de niveau d'études connu : il n'y a rien à analyser. "
                         "Déposer le fichier des diplômes dans input/diplomes.xlsx.")
    return rule_params, df


def detection(df: pd.DataFrame, rule_params: dict, feats=None) -> pd.DataFrame:
    """La détection, des groupes de collègues jusqu'à la priorité, dans le même ordre que
    src/detect_salary_anomalies.py. feats : les colonnes que regarde l'IA, si on lui en donne d'autres
    que d'habitude (voir entrainer_ia dans src/anomaly_signal_iforest.py)."""
    df = former_cohortes(df, rule_params)
    df = apply_rulebook(df, rule_params)
    df = ml_anomaly(df, rule_params, feats=feats)
    df = apply_ml_strong_signal(df, rule_params, feats=feats)
    return aggregate_risk(df, rule_params)


def virgule(x, decimales=2):
    """0.985 -> « 0,99 » ; 12345.6 -> « 12 346 » avec decimales=0 ; « 0,00 » plutôt que « -0,00 »."""
    if abs(x) < 0.5 * 10 ** -decimales:
        x = 0.0
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


def pour_cent(x, decimales=0):
    """0.034 -> « 3 % »."""
    return f"{virgule(x * 100, decimales)} %"


def ecrire_page(nom: str, titre: str, df: pd.DataFrame, corps: str, graphes: dict) -> Path:
    """Écrit la page dans output/analyse_diplomes/, sous un nom daté (une page de plus à chaque
    lancement, sans effacer les anciennes), et rend son chemin.
    - corps : le texte de la page, en HTML ;
    - graphes : pour chaque bloc <div id="..."> du corps, la liste des courbes Plotly et la mise en page.
    Plotly est recopié dans la page (depuis visualisation/vendor/) : elle s'ouvre sans internet."""
    maintenant = datetime.now()
    style = {"font": {"family": "Segoe UI, Arial, sans-serif", "color": "#4a2c1d"}, "paper_bgcolor": "white",
             "plot_bgcolor": "white", "separators": ", "}
    donnees = json.dumps({cle: {"data": courbes, "layout": {**style, **mise_en_page}}
                          for cle, (courbes, mise_en_page) in graphes.items()},
                         ensure_ascii=False).replace("<", "\\u003c")
    plotly_js = (VENDOR / "plotly.min.js").read_text(encoding="utf-8")
    # Le favicon Repères, le même que celui de la page d'exploration, du tableau de bord et de l'aide à la
    # décision : il est lu dans visualisation/favicon.svg, pour qu'il n'y en ait qu'un à modifier, et
    # recopié dans la page (quote l'écrit sous une forme qu'un lien accepte), car la page est un fichier
    # seul dans output/, sans le fichier du favicon à côté d'elle.
    favicon = quote((VENDOR.parent / "favicon.svg").read_text(encoding="utf-8").strip())
    html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>{titre}</title>
<link rel="icon" href="data:image/svg+xml,{favicon}" type="image/svg+xml">
<style>
body {{ font-family: "Segoe UI", Arial, sans-serif; color: #4a2c1d; max-width: 1100px; margin: 24px auto; padding: 0 16px; }}
h1 {{ font-size: 24px; }} h2 {{ font-size: 18px; margin-top: 36px; border-bottom: 3px solid #e9a21b; padding-bottom: 4px; }}
p, li {{ line-height: 1.5; }} .lire {{ color: #5b6b7d; }}
.constat {{ background: #fdf5e4; border-left: 4px solid #e9a21b; padding: 10px 14px; }}
table {{ border-collapse: collapse; margin: 10px 0; }} th, td {{ border: 1px solid #d9dde2; padding: 6px 12px; text-align: right; }}
th {{ background: #f4f5f7; }} .graphe {{ height: 420px; }}
</style><script>{plotly_js}</script></head><body>
<h1>{titre}</h1>
<p class="lire">Analyse du {maintenant:%d/%m/%Y à %H:%M}. {message_diplomes(df)}</p>
{corps}
<script>
const D = {donnees};
for (const [id, g] of Object.entries(D)) Plotly.newPlot(id, g.data, g.layout, {{displaylogo: false, responsive: true}});
</script></body></html>"""
    dossier = PROJET / "output" / "analyse_diplomes"
    dossier.mkdir(parents=True, exist_ok=True)
    page = dossier / f"{nom}_{maintenant:%Y-%m-%d_%H-%M-%S}.html"
    page.write_text(html, encoding="utf-8")
    return page
