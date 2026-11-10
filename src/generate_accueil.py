#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ÉCRAN D'ACCUEIL : UNE PAGE QUI OUVRE LES TROIS OUTILS
=====================================================

Ce fichier écrit accueil.html, à la racine du projet : trois cartes côte à côte, une par outil, dans
l'ordre où on s'en sert.
1. Explorer les données  -> visualisation/exploration_salaires.html (la visualisation en amont) ;
2. Détecter les anomalies -> le dernier tableau de bord de output/dashboard/ ;
3. Décider d'un salaire   -> l'aide à la décision (http://127.0.0.1:8765).
Chaque carte montre un aperçu de l'outil (images du dossier accueil/), trois chiffres clés et un bouton.

Pourquoi une page refaite à chaque détection, et pas une page fixe : le tableau de bord change de nom à
chaque lancement (il porte la date et l'heure), et les chiffres des cartes doivent être ceux de la
dernière détection. Le programme principal (src/detect_salary_anomalies.py) la refait donc en dernière
étape. La page s'ouvre d'un double-clic, sans Python ni internet.

Seule l'aide à la décision n'est pas une simple page : il faut d'abord lancer son programme
(python -m decision_support.app). La carte le rappelle.

Utilisation :
- depuis Python :
      from generate_accueil import generate_accueil
      generate_accueil(df, tableau_de_bord, projet)
- en ligne de commande, depuis le dossier du projet (elle relit output/detection/anomalies.xlsx et
  prend le tableau de bord le plus récent ; lancer d'abord src/detect_salary_anomalies.py) :
      python src/generate_accueil.py
"""

import html
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

# L'adresse de l'aide à la décision (le port par défaut de decision_support/app.py).
AIDE_DECISION = "http://127.0.0.1:8765"


def nombre(n, decimales=0):
    """12345.6 -> « 12 346 » ; 2.5 avec decimales=1 -> « 2,5 »."""
    return f"{n:,.{decimales}f}".replace(",", " ").replace(".", ",")


def chiffres(df: pd.DataFrame) -> dict:
    """Les chiffres clés des trois cartes, lus dans le tableau rendu par la détection."""
    salaire = df["Fixe_Annuel_MAD"]
    n = len(df)
    grilles = df.loc[df["Mid"].notna(), ["Job_Family", "Niveau"]].drop_duplicates()
    return {
        "effectif": n,
        "sous_min": (salaire < df["Min"]).sum() / n * 100 if n else 0.0,
        "au_dessus_max": (salaire > df["Max"]).sum() / n * 100 if n else 0.0,
        "critiques": int((df["Severity"] == "Critical").sum()),
        "majeures": int((df["Severity"] == "Major").sum()),
        "cout": float(df["Cout_Ajustement"].sum()),
        "grilles": len(grilles),
        "metiers": df["Job_Family"].nunique(),
        "niveaux": df["Niveau"].nunique(),
    }


def carte(lien, image, etiquette, numero, titre, texte, kpis, bouton, note=""):
    """Le HTML d'une carte. kpis : trois couples (valeur, libellé) ; un troisième élément « alerte » écrit
    la valeur en rouge."""
    cases = "".join(
        f'<div{" class=alerte" if len(k) > 2 else ""}><b>{html.escape(k[0])}</b><span>{html.escape(k[1])}</span></div>'
        for k in kpis)
    note = f'<p class="note">{note}</p>' if note else ""
    return f"""
  <a class="card" href="{html.escape(lien)}">
    <img class="shot" src="{html.escape(image)}" alt="">
    <div class="body">
      <p class="tag">{html.escape(etiquette)}</p>
      <h2><span class="num">{numero}</span>{html.escape(titre)}</h2>
      <p>{html.escape(texte)}</p>
      <div class="kpis">{cases}</div>{note}
      <span class="btn">{html.escape(bouton)} →</span>
    </div>
  </a>"""


def build_html(c: dict, lien_tableau: str, maintenant: datetime) -> str:
    cartes = (
        carte("visualisation/exploration_salaires.html", "accueil/exploration.png", "En amont", 1,
              "Explorer les données",
              "Qui sont les salariés, combien ils gagnent et où ils se situent dans la grille et le marché. "
              "On y dépose les trois fichiers.",
              [(nombre(c["effectif"]), "salariés"), (nombre(c["sous_min"], 1) + " %", "sous le Min"),
               (nombre(c["au_dessus_max"], 1) + " %", "au-dessus du Max")],
              "Ouvrir l'exploration")
        + carte(lien_tableau, "accueil/detection.png", "Détection", 2, "Détecter les anomalies",
                "Les salaires à traiter, par priorité, avec le signal de l'IA, le motif en clair et le coût "
                "d'ajustement.",
                [(nombre(c["critiques"]), "critiques", "alerte"), (nombre(c["majeures"]), "majeures"),
                 (nombre(c["cout"]), "kMAD d'ajustement")],
                "Ouvrir le tableau de bord")
        + carte(AIDE_DECISION, "accueil/decision.png", "Décision", 3, "Décider d'un salaire",
                "Pour un métier, un niveau et un profil : la fourchette proposée, la cible et le salaire "
                "attendu par le modèle.",
                [(nombre(c["grilles"]), "grilles"), (nombre(c["metiers"]), "métiers"),
                 (nombre(c["niveaux"]), "niveaux")],
                "Ouvrir l'aide à la décision",
                note="À lancer d'abord : <code>python -m decision_support.app</code>")
    )
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repères — Accueil</title>
<meta name="theme-color" content="#e9a21b">
<link rel="icon" href="visualisation/favicon.svg" type="image/svg+xml">
<style>
/* Charte Repères, la même que l'exploration, le tableau de bord et l'aide à la décision. Polices
   système seulement : la page s'ouvre sans internet. */
:root {{ --brand: #e9a21b; --brand-dark: #4a2c1d; --bg: #f3f4f6; --panel: #fff; --ink: #1f2328; --muted: #5f6670;
  --faint: #8b929b; --line: #dde0e4; --line-soft: #eceef1; --error: #b3261e; --radius: 4px;
  --font: "Segoe UI", system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 var(--font); font-variant-numeric: tabular-nums; }}
h1, h2, p {{ margin: 0; }}
a {{ color: inherit; text-decoration: none; }}
a:focus-visible {{ outline: 2px solid var(--brand); outline-offset: 2px; }}
code {{ font: 12px Consolas, "Courier New", monospace; background: #eef0f2; padding: 0 4px; border-radius: 2px; }}
.topbar {{ display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 0 32px; min-height: 60px;
  background: var(--panel); border-top: 4px solid var(--brand); border-bottom: 1px solid var(--line); }}
.brand {{ display: flex; align-items: center; gap: 10px; color: var(--brand-dark); font-size: 17px; font-weight: 700; }}
.brand-mark {{ width: 22px; height: 22px; background: var(--brand); position: relative; flex: none; }}
.brand-mark::after {{ content: ""; position: absolute; inset: 6px; background: var(--panel); }}
.brand-sub {{ font-size: 13px; font-weight: 400; color: var(--muted); padding-left: 10px; border-left: 1px solid var(--line); }}
.context {{ display: flex; gap: 28px; margin: 0; }}
.context dt {{ font-size: 11px; color: var(--faint); }}
.context dd {{ margin: 0; font-size: 13px; font-weight: 600; white-space: nowrap; }}
main {{ max-width: 1360px; margin: auto; padding: 28px 32px 40px; }}
.crumb {{ font-size: 12px; color: var(--faint); margin-bottom: 2px; }}
h1 {{ font-size: 22px; font-weight: 600; }}
.lead {{ color: var(--muted); margin-top: 6px; }}
.grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 24px; }}
.card {{ display: flex; flex-direction: column; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
  transition: box-shadow .15s, transform .15s, border-color .15s; }}
.card:hover {{ box-shadow: 0 10px 28px rgba(31, 35, 40, .12); transform: translateY(-2px); border-color: var(--brand); }}
.shot {{ display: block; width: 100%; height: 210px; object-fit: cover; object-position: top left;
  border-bottom: 1px solid var(--line); border-radius: var(--radius) var(--radius) 0 0; }}
.body {{ display: flex; flex-direction: column; gap: 12px; flex: 1; padding: 18px 20px 20px; }}
.tag {{ font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--faint); font-weight: 600; }}
h2 {{ display: flex; align-items: center; gap: 10px; font-size: 17px; font-weight: 600; }}
.num {{ display: inline-grid; place-items: center; width: 24px; height: 24px; background: var(--brand); color: #fff;
  font-size: 13px; font-weight: 700; border-radius: var(--radius); flex: none; }}
.body > p {{ color: var(--muted); }}
.kpis {{ display: grid; grid-template-columns: repeat(3, 1fr); margin-top: auto; border: 1px solid var(--line-soft); border-radius: var(--radius); }}
.kpis div {{ padding: 10px 12px; }}
.kpis div + div {{ border-left: 1px solid var(--line-soft); }}
.kpis b {{ display: block; font-size: 18px; font-weight: 600; }}
.kpis span {{ font-size: 11px; color: var(--faint); }}
.kpis .alerte b {{ color: var(--error); }}
.body > .note {{ font-size: 12px; color: var(--faint); }}
.btn {{ display: flex; align-items: center; height: 38px; padding: 0 16px; font-weight: 600; font-size: 13px;
  background: var(--brand-dark); color: #fff; border-radius: var(--radius); }}
.card:hover .btn {{ background: #3a2216; }}
footer {{ margin-top: 24px; font-size: 12px; color: var(--faint); }}
@media (max-width: 980px) {{ .grid {{ grid-template-columns: 1fr; }} .context {{ display: none; }} main {{ padding: 20px 16px 32px; }} }}
@media (prefers-reduced-motion: reduce) {{ .card {{ transition: none; }} .card:hover {{ transform: none; }} }}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand"><span class="brand-mark" aria-hidden="true"></span>Repères<span class="brand-sub">Rémunération</span></div>
  <dl class="context">
    <div><dt>Effectif analysé</dt><dd>{nombre(c["effectif"])} salariés</dd></div>
    <div><dt>Dernière détection</dt><dd>{maintenant:%d/%m/%Y à %H:%M}</dd></div>
    <div><dt>Montants</dt><dd>kMAD (milliers de MAD)</dd></div>
  </dl>
</header>
<main>
  <p class="crumb">Rémunération › Accueil</p>
  <h1>Les trois outils de la rémunération</h1>
  <p class="lead">Explorer les données, détecter les salaires à traiter, puis décider d'un salaire. Chaque carte ouvre l'outil.</p>
  <div class="grid">{cartes}
  </div>
  <footer>Chiffres de la dernière détection (src/detect_salary_anomalies.py). Les aperçus sont des images d'exemple.</footer>
</main>
</body>
</html>
"""


def generate_accueil(df: pd.DataFrame, tableau_de_bord, projet) -> Path:
    """Écrit accueil.html à la racine du projet et rend son chemin.
    - df : le tableau rendu par la détection (avec Severity et Cout_Ajustement) ;
    - tableau_de_bord : le fichier du tableau de bord vers lequel pointe la carte 2 ;
    - projet : le dossier du projet."""
    projet = Path(projet)
    # Le lien est écrit par rapport à la page, avec des « / » : il marche encore si on déplace ou copie
    # tout le dossier du projet, sous Windows comme ailleurs.
    lien = Path(os.path.relpath(tableau_de_bord, projet)).as_posix()
    sortie = projet / "accueil.html"
    sortie.write_text(build_html(chiffres(df), lien, datetime.now()), encoding="utf-8")
    return sortie


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/generate_accueil.py).
if __name__ == "__main__":
    projet = Path(__file__).resolve().parent.parent
    resultats = projet / "output" / "detection" / "anomalies.xlsx"
    tableaux = sorted((projet / "output" / "dashboard").glob("dashboard_anomalies_*.html"))
    if not resultats.exists() or not tableaux:
        raise SystemExit("Lancer d'abord la détection : python src/detect_salary_anomalies.py")
    # Les noms des tableaux de bord portent la date et l'heure : le dernier de la liste est le plus récent.
    print(f"Écran d'accueil : {generate_accueil(pd.read_excel(resultats), tableaux[-1], projet)}")
