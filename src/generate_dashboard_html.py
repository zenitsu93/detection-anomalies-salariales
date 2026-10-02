#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TABLEAU DE BORD HTML DES ANOMALIES
==================================

Ce fichier crée un tableau de bord HTML (graphiques Chart.js) à partir de :
- df : le DataFrame des salariés rendu par anomaly_recommandations.py, avec le score général
  (RiskScore) et la priorité (Severity) ajoutés par anomaly_score_general.py ;
- gg : le tableau rendu par anomaly_ecarts_hommes_femmes.py.
Il ne recalcule rien : il compte et affiche. Un clic sur une barre ou un point affiche les salariés
concernés, avec un export CSV.

Un salarié est « à traiter » si sa priorité est Critical, Major ou Minor : les « Info » n'ont rien à
faire.

Utilisation :
- depuis Python :
      from generate_dashboard_html import generate_dashboard
      generate_dashboard(df, gg, "output/dashboard")
- en ligne de commande, depuis le dossier du projet :
      python src/generate_dashboard_html.py
  Le tableau de bord est enregistré dans output/dashboard/, sous un nom daté
  (dashboard_anomalies_AAAA-MM-JJ_HH-MM-SS.html), à ouvrir avec un navigateur. Chaque lancement
  ajoute un fichier sans effacer les précédents.
"""

import json
from datetime import datetime
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from anomaly_pretraitement import preparer_employes
from anomaly_cohortes import former_cohortes
from anomaly_regles import apply_rulebook
from anomaly_signal_iforest import ml_anomaly
from anomaly_signal_fort import apply_ml_strong_signal
from anomaly_score_general import aggregate_risk
from anomaly_recommandations import recommendations
from anomaly_ecarts_hommes_femmes import gender_gap_analysis

CHARTJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.1/chart.umd.min.js"

# Charte Repères : or et brun pour la marque (brun aussi pour les montants), ardoise pour les effectifs.
GOLD = "#e9a21b"
BROWN = "#4a2c1d"
SLATE = "#5b6b7d"

# Priorités : rouge → orange → or selon la gravité, gris clair pour « Info », qui n'a rien à faire.
SEVERITY_ORDER = ["Critical", "Major", "Minor", "Info"]
STATUS = {"Critical": "#b3261e", "Major": "#d9731f", "Minor": GOLD, "Info": "#c4c9cf"}
SEVERITY_FR = {"Critical": "Critique", "Major": "Majeure", "Minor": "Mineure", "Info": "Info (sans action)"}

# Les trois courbes du score général : brun cuivré pour le score général, or pour les règles, bleu
# pour l'IA. Trois teintes choisies pour rester distinctes, y compris pour un lecteur daltonien.
SCORE_COLORS = {"RiskScore": "#9a5530", "Rule_Score": GOLD, "ML_AnomalyScore": "#3d6fa8"}

# Les étiquettes traduites pour l'écran ; le code d'origine reste visible dans l'infobulle.
FLAG_FR = {
    "OUT_OF_BAND": "Hors grille",
    "COMPA_RATIO": "Position dans la grille",
    "MARKET_GAP": "Écart au marché",
    "PEER_OUTLIER": "Écart aux collègues",
    "ML_STRONG_SIGNAL": "Signal statistique fort",
}
# Les colonnes de la liste des salariés (clic sur une barre), et leur nom affiché.
COL_FR = {
    "Matricule": "Matricule", "Entite_N1": "Pôle", "Job_Family": "Métier", "Job_Title": "Poste",
    "Grade": "Grade", "Sexe": "Sexe", "Severity": "Priorité", "RiskScore": "Score général",
    "CompaRatio": "CompaRatio", "Rule_Flags": "Signaux",
    "Rule_Score": "Score de règles", "ML_AnomalyScore": "Score IA", "Reco": "Recommandation",
    "Cout_Ajustement": "Coût d'ajustement",
}


def fmt_int(n):
    return f"{int(round(n)):,}".replace(",", " ")


def fmt_num(x):
    """12345.6 -> « 12 345,6 » ; 5.0 -> « 5 »."""
    return f"{x:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")


def build_data(df: pd.DataFrame, gg: pd.DataFrame) -> dict:
    """Compte ce que les graphiques affichent."""
    a_traiter = df["Severity"] != "Info"
    flags = df["Rule_Flags"].str.split(";").explode()
    flags = flags[flags != ""].value_counts()
    # Salariés à traiter par pôle et par priorité, les pôles les plus concernés en premier.
    pole = pd.crosstab(df.loc[a_traiter, "Entite_N1"], df.loc[a_traiter, "Severity"])
    pole = pole.reindex(columns=SEVERITY_ORDER[:3], fill_value=0)
    pole = pole.loc[pole.sum(axis=1).sort_values(ascending=False).index]
    job = df.loc[a_traiter, "Job_Family"].value_counts().head(10)
    cost = df.groupby("Entite_N1")["Cout_Ajustement"].sum().sort_values(ascending=False)
    # Les trois scores comptés par tranches de 10 (tout ce qui dépasse 90 va dans la dernière). Même
    # arrondi et même calcul que la liste affichée au clic, pour que les deux comptes collent.
    scores = [{"code": col, "label": COL_FR[col], "color": couleur,
               "data": np.floor(df[col].round(2) / 10).clip(upper=9).astype(int)
                         .value_counts().reindex(range(10), fill_value=0).tolist()}
              for col, couleur in SCORE_COLORS.items()]
    # Tous les écarts hommes / femmes (le choix des 10 plus marqués ou d'un grade se fait dans la page),
    # avec le nombre de femmes et d'hommes : un écart sur 3 personnes ne pèse pas comme un écart sur 300.
    # Un métier + grade sans femme ou sans homme n'a pas d'écart : il est écarté.
    effectifs = df.groupby(["Job_Family", "Grade", "Sexe"]).size().unstack(fill_value=0).reset_index()
    gap = gg.dropna(subset=["M_div_F"]).merge(effectifs, on=["Job_Family", "Grade"])
    gap["Ecart_pct"] = (gap["M_div_F"] - 1) * 100
    gap = gap[["Job_Family", "Grade", "Median_F", "Median_M", "F", "M", "Ecart_pct"]]
    gap = gap.round({"Median_F": 2, "Median_M": 2, "Ecart_pct": 1})

    # La liste des salariés : cases vides en None, sinon le JSON serait invalide.
    rec = df[list(COL_FR)].round(2)
    rec = rec.astype(object).where(rec.notna(), None)

    return {
        "kpis": {
            "effectif": len(df),
            "a_traiter": int(a_traiter.sum()),
            **{s: int((df["Severity"] == s).sum()) for s in SEVERITY_ORDER[:3]},
            "cout_total": float(df["Cout_Ajustement"].sum()),
        },
        "pole": {
            "labels": pole.index.tolist(),
            # « code » garde le nom anglais (Critical...) pour retrouver les salariés au clic ; « label »
            # est le texte affiché.
            "datasets": [{"code": s, "label": SEVERITY_FR[s], "color": STATUS[s],
                          "data": pole[s].astype(int).tolist()} for s in SEVERITY_ORDER[:3]],
        },
        "job": {"labels": job.index.tolist(), "data": job.tolist()},
        "cost": {"labels": cost.index.tolist(), "data": cost.round(1).tolist()},
        "flags": {"labels": [FLAG_FR.get(f, f) for f in flags.index], "codes": flags.index.tolist(),
                  "data": flags.tolist()},
        "scores": {"labels": [f"{b}-{b + 10}" for b in range(0, 100, 10)], "datasets": scores},
        "gap": gap.to_dict("records"),
        "records": {"cols": list(COL_FR), "rows": rec.values.tolist()},
    }


def table_html(entetes, lignes):
    head = "".join(f"<th>{e}</th>" for e in entetes)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(v)}</td>" if isinstance(v, str) else f'<td class="num">{fmt_num(v)}</td>'
                         for v in ligne) + "</tr>"
        for ligne in lignes
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_html(data: dict, maintenant: datetime) -> str:
    kpis = data["kpis"]
    # Un « < » dans un libellé ne doit pas pouvoir fermer la balise <script>.
    data_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    names_json = json.dumps({"cols": COL_FR, "flags": FLAG_FR, "sev": SEVERITY_FR}, ensure_ascii=False).replace("<", "\\u003c")
    # La même heure que dans le nom du fichier.
    generated = maintenant.strftime("%d/%m/%Y à %H:%M")
    pct = kpis["a_traiter"] / kpis["effectif"] * 100 if kpis["effectif"] else 0.0

    s, p = data["scores"], data["pole"]
    # Plus de tableau des écarts hommes / femmes : le graphique par grade le remplace.
    tables_html = "".join(
        f'<details class="data-toggle"><summary>{titre}</summary>'
        f'<div class="table-wrap">{table_html(entetes, lignes)}</div></details>'
        for titre, entetes, lignes in [
            ("Anomalies à traiter par pôle", ["Pôle"] + [d["label"] for d in p["datasets"]],
             zip(p["labels"], *[d["data"] for d in p["datasets"]])),
            ("Top métiers", ["Métier", "Salariés à traiter"], zip(data["job"]["labels"], data["job"]["data"])),
            ("Coût par pôle", ["Pôle", "Coût d'ajustement"], zip(data["cost"]["labels"], data["cost"]["data"])),
            ("Signaux déclencheurs", ["Signal", "Salariés"], zip(data["flags"]["labels"], data["flags"]["data"])),
            ("Score général", ["Tranche"] + [d["label"] for d in s["datasets"]],
             zip(s["labels"], *[d["data"] for d in s["datasets"]])),
        ]
    )

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repères — Anomalies salariales</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='3' fill='%23e9a21b'/%3E%3Crect x='9' y='9' width='14' height='14' fill='%23fff'/%3E%3Crect x='15' y='4' width='2' height='24' fill='%234a2c1d'/%3E%3C/svg%3E">
<script src="{CHARTJS_URL}"></script>
<style>
/* Charte Repères. */
:root {{
  --brand: {GOLD}; --brand-dark: {BROWN};
  --bg: #f3f4f6; --panel: #fff; --panel-head: #fafafa;
  --ink: #1f2328; --muted: #5f6670; --faint: #8b929b;
  --line: #dde0e4; --line-soft: #eceef1;
  --radius: 4px; --font: "Segoe UI", system-ui, sans-serif;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 var(--font); font-variant-numeric: tabular-nums; }}
h1, h2, h3, p {{ margin: 0; }}

.topbar {{ display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 0 32px; min-height: 60px;
  background: var(--panel); border-top: 4px solid var(--brand); border-bottom: 1px solid var(--line); }}
.brand {{ display: flex; align-items: center; gap: 10px; color: var(--brand-dark); font-size: 17px; font-weight: 700; }}
.brand-mark {{ width: 22px; height: 22px; background: var(--brand); position: relative; }}
.brand-mark::after {{ content: ""; position: absolute; inset: 6px; background: var(--panel); }}
.brand-sub {{ font-size: 13px; font-weight: 400; color: var(--muted); padding-left: 10px; border-left: 1px solid var(--line); }}
.context {{ display: flex; gap: 28px; margin: 0; }}
.context dt {{ font-size: 11px; color: var(--faint); }}
.context dd {{ margin: 0; font-size: 13px; font-weight: 600; white-space: nowrap; }}

main {{ max-width: 1320px; margin: auto; padding: 24px 32px 32px; }}
.page-head {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin-bottom: 20px; }}
.crumb {{ font-size: 12px; color: var(--faint); margin-bottom: 2px; }}
h1 {{ font-size: 22px; font-weight: 600; }}
.page-hint {{ font-size: 13px; color: var(--muted); }}

.panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); min-width: 0; }}
.panel-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 16px;
  background: var(--panel-head); border-bottom: 1px solid var(--line); border-radius: var(--radius) var(--radius) 0 0; }}
.panel-title {{ font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .4px; }}
.panel-unit {{ font-size: 12px; color: var(--faint); }}
.panel-body {{ padding: 16px; }}
.note {{ font-size: 12px; color: var(--muted); margin-top: 10px; }}

.kpis {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin: 0 0 16px; border-left: 4px solid var(--brand); }}
.kpis div {{ padding: 16px 20px; }}
.kpis div + div {{ border-left: 1px solid var(--line-soft); }}
.kpis dt {{ font-size: 12px; color: var(--muted); }}
.kpis dd {{ margin: 2px 0 0; font-size: 24px; font-weight: 600; white-space: nowrap; }}
.kpis dd small {{ display: block; font-size: 12px; font-weight: 400; color: var(--faint); }}
.kpis .sev {{ display: inline-block; width: 8px; height: 8px; margin-right: 6px; vertical-align: 2px; }}
.kpis .critical {{ color: {STATUS['Critical']}; }}
.sev-tag {{ display: inline-block; padding: 0 6px; border-radius: 2px; font-size: 12px; font-weight: 600; }}

.grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin-bottom: 16px; }}
.full {{ grid-column: 1 / -1; }}
.chart-box {{ position: relative; width: 100%; }}
.h-sm {{ height: 240px; }}
.h-md {{ height: 300px; }}
.h-lg {{ height: 360px; }}
.h-xl {{ height: 520px; }}
/* Boutons de choix des écarts hommes / femmes : celui qui est affiché est foncé. */
.views {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
.views button[aria-pressed="true"] {{ background: var(--brand-dark); border-color: var(--brand-dark); color: #fff; }}

details.data-toggle {{ border-top: 1px solid var(--line-soft); }}
details.data-toggle summary {{ cursor: pointer; padding: 10px 16px; font-size: 13px; }}
details.data-toggle[open] summary {{ font-weight: 600; }}
.table-wrap {{ overflow-x: auto; padding: 0 16px 12px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; font-size: 12px; font-weight: 600; color: var(--muted); padding: 8px 12px; border-bottom: 1px solid var(--line); background: var(--panel); white-space: nowrap; }}
td {{ padding: 8px 12px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }}
.num {{ text-align: right; }}
.data-panel summary {{ list-style: none; }}

.overlay {{ position: fixed; inset: 0; background: rgba(31,35,40,.45); display: flex; align-items: flex-start; justify-content: center; padding: 5vh 16px; z-index: 50; }}
.overlay[hidden] {{ display: none; }}
.overlay .panel {{ width: 100%; max-width: 1100px; max-height: 88vh; display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,.2); }}
.overlay h3 {{ font-size: 15px; font-weight: 600; }}
.overlay .sub {{ font-size: 12px; color: var(--muted); }}
.overlay .panel-body {{ overflow: auto; padding: 0; }}
.overlay th {{ position: sticky; top: 0; }}
.head-actions {{ display: flex; gap: 8px; flex: none; }}
button {{ font: 500 13px var(--font); height: 32px; padding: 0 12px; background: var(--panel); color: var(--ink);
  border: 1px solid #c4c9cf; border-radius: var(--radius); cursor: pointer; }}
button:hover {{ background: var(--panel-head); border-color: var(--faint); }}
button:focus-visible, summary:focus-visible {{ outline: 2px solid var(--brand); outline-offset: 2px; }}

footer {{ margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--line); font-size: 12px; color: var(--faint); }}

@media (max-width: 1000px) {{
  .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .kpis div:nth-child(odd) {{ border-left: 0; }}
  .kpis div {{ border-top: 1px solid var(--line-soft); }}
  .grid {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 700px) {{
  .topbar {{ flex-direction: column; align-items: flex-start; gap: 8px; padding: 10px 16px; }}
  .brand-sub {{ display: none; }}
  .context {{ gap: 16px; flex-wrap: wrap; }}
  main {{ padding: 16px; }}
  .page-head {{ flex-direction: column; align-items: flex-start; }}
  .kpis dd {{ font-size: 20px; }}
}}
@media print {{
  body {{ background: #fff; }}
  .panel {{ break-inside: avoid; }}
  .page-hint, .overlay {{ display: none; }}
}}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand"><span class="brand-mark" aria-hidden="true"></span>Repères<span class="brand-sub">Détection des anomalies salariales</span></div>
  <dl class="context">
    <div><dt>Effectif analysé</dt><dd>{fmt_int(kpis['effectif'])} salariés</dd></div>
    <div><dt>Montants</dt><dd>Unité source</dd></div>
    <div><dt>Généré le</dt><dd>{generated}</dd></div>
  </dl>
</header>
<main>
  <div class="page-head">
    <div><p class="crumb">Rémunération › Anomalies</p><h1>Tableau de bord des anomalies</h1></div>
    <p class="page-hint">Cliquez une barre ou un point pour afficher les salariés concernés.</p>
  </div>

  <dl class="panel kpis">
    <div><dt>À traiter</dt><dd>{fmt_num(round(pct, 1))} %<small>{fmt_int(kpis['a_traiter'])} salariés</small></dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Critical']}"></span>Critiques</dt><dd class="critical">{fmt_int(kpis['Critical'])}</dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Major']}"></span>Majeures</dt><dd>{fmt_int(kpis['Major'])}</dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Minor']}"></span>Mineures</dt><dd>{fmt_int(kpis['Minor'])}</dd></div>
    <div><dt>Coût d'ajustement total</dt><dd>{fmt_int(kpis['cout_total'])}<small>unité source</small></dd></div>
  </dl>

  <div class="grid">
    <section class="panel full">
      <div class="panel-head"><h2 class="panel-title">Anomalies à traiter par pôle</h2><span class="panel-unit">salariés</span></div>
      <div class="panel-body"><div class="chart-box h-sm"><canvas id="chart-pole"></canvas></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Top 10 métiers concernés</h2><span class="panel-unit">salariés à traiter</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-job"></canvas></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Coût d'ajustement par pôle</h2><span class="panel-unit">unité source</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-cost"></canvas></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Signaux déclencheurs</h2><span class="panel-unit">salariés</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-flags"></canvas></div>
        <p class="note">Un salarié peut déclencher plusieurs signaux.</p></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Score général</h2><span class="panel-unit">salariés par tranche de score</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-risk"></canvas></div>
        <p class="note">Le score général réunit le score de règles et le score IA ; c'est lui qui fixe la priorité.</p></div>
    </section>
    <section class="panel full">
      <div class="panel-head"><h2 class="panel-title">Écarts de salaire hommes / femmes</h2><span class="panel-unit">par métier et grade</span></div>
      <div class="panel-body">
        <div class="views" id="gap-views" role="group" aria-label="Écarts à afficher"></div>
        <div class="chart-box h-xl"><canvas id="chart-gap"></canvas></div>
        <p class="note">Chaque barre compare le salaire médian (celui du milieu) des hommes à celui des femmes, à métier
          et grade égaux : +10 % veut dire que les hommes touchent 10 % de plus. Sous chaque métier, le nombre de
          femmes et d'hommes comparés : sur quelques personnes, un seul salaire suffit à créer un gros écart. Un métier
          sans femme ou sans homme dans le grade n'apparaît pas.</p>
      </div>
    </section>
    <details class="panel full data-panel">
      <summary class="panel-head"><h2 class="panel-title">Données détaillées</h2><span class="panel-unit">afficher</span></summary>
      {tables_html}
    </details>
  </div>

  <footer>Restitution des résultats de la détection (src), sans recalcul.</footer>
</main>

<div class="overlay" id="panel-overlay" hidden>
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="panel-title">
    <div class="panel-head">
      <div><h3 id="panel-title">—</h3><div class="sub" id="panel-sub"></div></div>
      <div class="head-actions"><button id="panel-export" type="button">Exporter (CSV)</button><button id="panel-close" type="button" aria-label="Fermer">Fermer</button></div>
    </div>
    <div class="panel-body" id="panel-body"></div>
  </div>
</div>

<script>
const DATA = {data_json};
const NAMES = {names_json};
const STATUS = {json.dumps(STATUS)};

// ---- Liste des salariés concernés (clic sur une barre) ----
const RCOLS = DATA.records.cols, RROWS = DATA.records.rows, RIDX = {{}};
RCOLS.forEach((c, i) => RIDX[c] = i);
const MAX_ROWS_SHOWN = 300;
const NUM = new Intl.NumberFormat('fr-FR', {{ maximumFractionDigits: 2 }});
const aTraiter = r => r[RIDX.Severity] !== 'Info';

const overlay = document.getElementById('panel-overlay');
const panelTitle = document.getElementById('panel-title');
const panelSub = document.getElementById('panel-sub');
const panelBody = document.getElementById('panel-body');
let lastMatches = [], lastTitle = '';
document.getElementById('panel-close').addEventListener('click', closePanel);
overlay.addEventListener('click', e => {{ if (e.target === overlay) closePanel(); }});
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closePanel(); }});

function closePanel() {{ overlay.hidden = true; }}

function escapeText(value) {{
  const cell = document.createElement('span');
  cell.textContent = value === null ? '' : String(value);
  return cell.innerHTML;
}}
function cellHtml(col, v) {{
  if (v === null || v === undefined) return '<td></td>';
  if (col === 'Severity') return '<td><span class="sev-tag" style="background:' + STATUS[v] + '22;color:' + STATUS[v] + '">' + escapeText(NAMES.sev[v] || v) + '</span></td>';
  if (col === 'Rule_Flags') return '<td>' + escapeText(String(v).split(';').filter(Boolean).map(f => NAMES.flags[f] || f).join(', ')) + '</td>';
  if (typeof v === 'number') return '<td class="num">' + NUM.format(v) + '</td>';
  return '<td>' + escapeText(v) + '</td>';
}}

function showPopulation(title, predicate) {{
  const matches = RROWS.filter(predicate);
  lastMatches = matches; lastTitle = title;
  panelTitle.textContent = title;
  panelSub.textContent = NUM.format(matches.length) + ' salarié(s) concerné(s)'
    + (matches.length > MAX_ROWS_SHOWN ? ' — ' + MAX_ROWS_SHOWN + ' premiers affichés, export complet en CSV' : '');
  if (!matches.length) {{
    panelBody.innerHTML = '<p class="note" style="padding:16px">Aucun salarié ne correspond à cette sélection.</p>';
  }} else {{
    const head = RCOLS.map(c => '<th>' + escapeText(NAMES.cols[c] || c) + '</th>').join('');
    const body = matches.slice(0, MAX_ROWS_SHOWN).map(r => '<tr>' + r.map((v, i) => cellHtml(RCOLS[i], v)).join('') + '</tr>').join('');
    panelBody.innerHTML = '<table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table>';
  }}
  overlay.hidden = false;
}}

// Export de TOUTE la sélection. « ; » et BOM au début : ce qu'attend Excel en français.
document.getElementById('panel-export').addEventListener('click', () => {{
  const q = v => {{ const s = v === null || v === undefined ? '' : String(v); return /[";\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }};
  const lines = [RCOLS.map(c => q(NAMES.cols[c] || c)).join(';')]
    .concat(lastMatches.map(r => r.map(v => q(typeof v === 'number' ? String(v).replace('.', ',') : v)).join(';')));
  const url = URL.createObjectURL(new Blob(['\\ufeff' + lines.join('\\r\\n')], {{ type: 'text/csv;charset=utf-8' }}));
  const a = document.createElement('a'); a.href = url;
  a.download = 'salaries_' + lastTitle.normalize('NFD').replace(/[^\\w]+/g, '_').replace(/^_|_$/g, '').toLowerCase() + '.csv';
  a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}});

// ---- Graphiques ----
function merge(base, extra) {{
  for (const k in extra) {{
    const v = extra[k];
    if (v && typeof v === 'object' && !Array.isArray(v) && base[k] && typeof base[k] === 'object') merge(base[k], v);
    else base[k] = v;
  }}
  return base;
}}
Chart.defaults.color = '#5f6670';
Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
Chart.defaults.font.size = 12;
const GRID = '#eceef1';
function baseOptions(extra) {{
  return merge({{
    locale: 'fr-FR',
    responsive: true,
    maintainAspectRatio: false,
    animation: {{ duration: 400 }},
    onHover: (evt, els) => {{ evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ backgroundColor: '#1f2328', padding: 10, cornerRadius: 3, displayColors: false }},
    }},
    scales: {{
      x: {{ grid: {{ color: GRID }}, border: {{ display: false }} }},
      y: {{ grid: {{ color: GRID }}, border: {{ display: false }} }},
    }},
  }}, extra);
}}
const shortTicks = {{ callback(v) {{ const l = this.getLabelForValue(v); return innerWidth < 600 && l.length > 16 ? l.slice(0, 15) + '…' : l; }} }};
const hbar = (color, extra) => merge({{ backgroundColor: color, borderRadius: 2, maxBarThickness: 18 }}, extra || {{}});
const pick = (els, fn) => {{ if (els.length) fn(els[0].index, els[0].datasetIndex); }};
// Réglages des barres horizontales (tous les graphiques sauf le score général).
const hOptions = extra => baseOptions(merge({{ indexAxis: 'y', scales: {{ y: {{ grid: {{ display: false }}, ticks: shortTicks }} }} }}, extra));

// Une barre par pôle, découpée par priorité ; une priorité sans aucun salarié n'est pas affichée.
const poleSets = DATA.pole.datasets.filter(d => d.data.some(v => v > 0));
new Chart(document.getElementById('chart-pole'), {{
  type: 'bar',
  data: {{ labels: DATA.pole.labels, datasets: poleSets.map(d => hbar(d.color, {{ label: d.label, data: d.data }})) }},
  options: hOptions({{
    plugins: {{ legend: {{ display: true, position: 'top', align: 'start', labels: {{ boxWidth: 10, boxHeight: 10, padding: 16 }} }},
               tooltip: {{ displayColors: true }} }},
    scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }},
    onClick: (evt, els) => pick(els, (i, d) => {{
      const pole = DATA.pole.labels[i], sev = poleSets[d];
      showPopulation(pole + ' — ' + sev.label, r => r[RIDX.Entite_N1] === pole && r[RIDX.Severity] === sev.code);
    }}),
  }}),
}});

new Chart(document.getElementById('chart-job'), {{
  type: 'bar',
  data: {{ labels: DATA.job.labels, datasets: [hbar('{SLATE}', {{ data: DATA.job.data }})] }},
  options: hOptions({{ onClick: (evt, els) => pick(els, i => {{
    const label = DATA.job.labels[i];
    showPopulation('Métier : ' + label, r => r[RIDX.Job_Family] === label && aTraiter(r));
  }}) }}),
}});

new Chart(document.getElementById('chart-cost'), {{
  type: 'bar',
  data: {{ labels: DATA.cost.labels, datasets: [hbar('{BROWN}', {{ data: DATA.cost.data }})] }},
  options: hOptions({{ onClick: (evt, els) => pick(els, i => {{
    const label = DATA.cost.labels[i];
    showPopulation("Coût d'ajustement : " + label, r => r[RIDX.Entite_N1] === label && r[RIDX.Cout_Ajustement] > 0);
  }}) }}),
}});

new Chart(document.getElementById('chart-flags'), {{
  type: 'bar',
  data: {{ labels: DATA.flags.labels, datasets: [hbar('{SLATE}', {{ data: DATA.flags.data }})] }},
  options: hOptions({{
    plugins: {{ tooltip: {{ callbacks: {{ title: items => items[0].label + ' (' + DATA.flags.codes[items[0].dataIndex] + ')' }} }} }},
    onClick: (evt, els) => pick(els, i => {{
      const code = DATA.flags.codes[i];
      showPopulation('Signal : ' + DATA.flags.labels[i], r => r[RIDX.Rule_Flags].split(';').includes(code));
    }}),
  }}),
}});

// Une courbe par score : combien de salariés tombent dans chaque tranche de 10 points.
const tranche = v => Math.min(Math.floor(v / 10), 9);
new Chart(document.getElementById('chart-risk'), {{
  type: 'line',
  data: {{ labels: DATA.scores.labels, datasets: DATA.scores.datasets.map((s, k) => ({{
    label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color,
    // Le score général (le premier), celui qui fixe la priorité, en trait plus épais.
    borderWidth: k ? 2 : 3, pointRadius: k ? 4 : 5, pointHoverRadius: 7, pointBorderColor: '#fff', pointBorderWidth: 2,
  }})) }},
  options: baseOptions({{
    // L'infobulle donne les trois scores de la tranche survolée.
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: true, position: 'top', align: 'start', labels: {{ usePointStyle: true, boxWidth: 8, boxHeight: 8, padding: 16 }} }},
      tooltip: {{ displayColors: true, callbacks: {{
        title: items => {{ const b = items[0].dataIndex * 10; return 'Score de ' + b + (b < 90 ? ' à moins de ' + (b + 10) : ' à 100'); }},
        label: c => c.dataset.label + ' : ' + NUM.format(c.parsed.y) + ' salariés',
      }} }},
    }},
    scales: {{
      x: {{ grid: {{ display: false }}, title: {{ display: true, text: 'Score sur 100, par tranche de 10 points' }} }},
      y: {{ beginAtZero: true, title: {{ display: true, text: 'Nombre de salariés' }} }},
    }},
    // Le clic retient le point le plus proche, donc une seule courbe.
    onClick: (evt, els, chart) => pick(chart.getElementsAtEventForMode(evt, 'nearest', {{ intersect: false, axis: 'xy' }}, false), (i, d) => {{
      const s = DATA.scores.datasets[d];
      showPopulation(s.label + ' ' + DATA.scores.labels[i], r => tranche(r[RIDX[s.code]]) === i);
    }}),
  }}),
}});

// ---- Écarts hommes / femmes : les 10 plus marqués, puis un bouton par grade ----
const GAP = DATA.gap;
const plural = (n, mot) => n + ' ' + mot + (n > 1 ? 's' : '');
const pctText = v => (v > 0 ? '+' : '') + NUM.format(v) + ' %';
const gapName = (r, avecGrade) => r.Job_Family + (avecGrade ? ' · grade ' + r.Grade : '');
// La même échelle pour toutes les vues : deux barres de même longueur montrent le même écart, d'un
// grade à l'autre. La marge de 20 % laisse la place d'écrire l'écart au bout de la plus longue barre ;
// arrondir à 20 près garde des graduations régulières (-40 %, -20 %, 0 %...).
const gapMax = Math.ceil(Math.max(...GAP.map(r => Math.abs(r.Ecart_pct))) * 1.2 / 20) * 20;
const gapViews = [{{ name: 'Les 10 plus marqués', rows: [...GAP].sort((a, b) => Math.abs(b.Ecart_pct) - Math.abs(a.Ecart_pct)).slice(0, 10) }}]
  .concat([...new Set(GAP.map(r => r.Grade))].sort((a, b) => a - b).map(g => ({{
    // Dans un grade, du plus favorable aux hommes (en haut) au plus favorable aux femmes (en bas).
    name: 'Grade ' + g, grade: g, rows: GAP.filter(r => r.Grade === g).sort((a, b) => b.Ecart_pct - a.Ecart_pct),
  }})));
let gapRows = [];

// Écrit l'écart au bout de chaque barre, et le sens de lecture de part et d'autre du zéro.
const gapLabels = {{
  id: 'gapLabels',
  afterDatasetsDraw(chart) {{
    const {{ ctx, chartArea, scales: {{ x }} }} = chart, zero = x.getPixelForValue(0), y = chartArea.top - 14;
    ctx.save();
    ctx.textBaseline = 'middle';
    ctx.font = '600 12px ' + Chart.defaults.font.family;
    ctx.fillStyle = '#1f2328';
    chart.getDatasetMeta(0).data.forEach((bar, i) => {{
      if (!gapRows[i]) return;
      const v = gapRows[i].Ecart_pct;
      ctx.textAlign = v < 0 ? 'right' : 'left';
      ctx.fillText(pctText(v), bar.x + (v < 0 ? -6 : 6), bar.y);
    }});
    ctx.font = '12px ' + Chart.defaults.font.family;
    ctx.fillStyle = '{GOLD}'; ctx.fillRect(zero - 18, y - 5, 10, 10);
    ctx.fillStyle = '{SLATE}'; ctx.fillRect(zero + 8, y - 5, 10, 10);
    ctx.fillStyle = '#5f6670';
    ctx.textAlign = 'right'; ctx.fillText('Femmes mieux payées', zero - 24, y);
    ctx.textAlign = 'left'; ctx.fillText('Hommes mieux payés', zero + 24, y);
    ctx.restore();
  }},
}};

const gapChart = new Chart(document.getElementById('chart-gap'), {{
  type: 'bar',
  data: {{ labels: [], datasets: [hbar([], {{ data: [] }})] }},
  plugins: [gapLabels],
  options: hOptions({{
    layout: {{ padding: {{ top: 24 }} }},
    plugins: {{ tooltip: {{ callbacks: {{
      title: items => gapName(gapRows[items[0].dataIndex], true),
      label: c => {{
        const r = gapRows[c.dataIndex];
        return ['Médiane femmes : ' + NUM.format(r.Median_F) + ' (' + plural(r.F, 'femme') + ')',
                'Médiane hommes : ' + NUM.format(r.Median_M) + ' (' + plural(r.M, 'homme') + ')',
                'Les hommes touchent ' + NUM.format(Math.abs(r.Ecart_pct)) + ' % de ' + (r.Ecart_pct < 0 ? 'moins' : 'plus') + ' que les femmes'];
      }},
    }} }} }},
    scales: {{
      x: {{ min: -gapMax, max: gapMax,
            ticks: {{ callback: v => (v > 0 ? '+' : '') + v + ' %' }},
            // Le zéro (pas d'écart) en trait plus foncé.
            grid: {{ color: c => c.tick.value === 0 ? '#8b929b' : GRID }},
            title: {{ display: true, text: 'Salaire médian des hommes comparé à celui des femmes (en %)' }} }},
      y: {{ title: {{ display: true }} }},
    }},
    onClick: (evt, els) => pick(els, i => {{
      const r = gapRows[i];
      showPopulation(gapName(r, true), x => x[RIDX.Job_Family] === r.Job_Family && x[RIDX.Grade] === r.Grade);
    }}),
  }}),
}});

function showGapView(view, button) {{
  gapRows = view.rows;
  // Deux lignes sous chaque barre : le métier (et le grade s'ils sont mélangés), puis les effectifs.
  gapChart.data.labels = gapRows.map(r => [gapName(r, !view.grade), plural(r.F, 'femme') + ' · ' + plural(r.M, 'homme')]);
  gapChart.data.datasets[0].data = gapRows.map(r => r.Ecart_pct);
  // Ardoise = hommes mieux payés, or = femmes mieux payées.
  gapChart.data.datasets[0].backgroundColor = gapRows.map(r => r.Ecart_pct > 0 ? '{SLATE}' : '{GOLD}');
  gapChart.options.scales.y.title.text = view.grade ? 'Métiers du grade ' + view.grade : 'Métier et grade';
  gapChart.update();
  viewButtons.forEach(b => b.setAttribute('aria-pressed', b === button));
}}
const viewButtons = gapViews.map(view => {{
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = view.name;
  b.addEventListener('click', () => showGapView(view, b));
  document.getElementById('gap-views').appendChild(b);
  return b;
}});
showGapView(gapViews[0], viewButtons[0]);
</script>
</body>
</html>
"""


def generate_dashboard(df: pd.DataFrame, gg: pd.DataFrame, dossier) -> Path:
    """Crée le tableau de bord à partir des deux tableaux et l'enregistre dans dossier.

    Le nom du fichier porte la date et l'heure (dashboard_anomalies_2026-10-02_14-35-08.html) : un
    nouveau lancement ne remplace pas le tableau de bord précédent, et les noms se rangent d'eux-mêmes
    du plus ancien au plus récent.
    """
    maintenant = datetime.now()
    out_html = Path(dossier) / f"dashboard_anomalies_{maintenant:%Y-%m-%d_%H-%M-%S}.html"
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(build_html(build_data(df, gg), maintenant), encoding="utf-8")
    return out_html


# Ce bloc ne s'exécute que si l'on lance CE fichier directement (python src/generate_dashboard_html.py),
# pas quand un autre programme fait « from generate_dashboard_html import ... ».
if __name__ == "__main__":
    # Le dossier du projet : deux crans au-dessus de ce fichier (src/generate_dashboard_html.py).
    projet = Path(__file__).resolve().parent.parent

    # Les réglages : la partie « rules: » du fichier de règles.
    with open(projet / "config" / "rules.yaml", encoding="utf-8") as fichier:
        rule_params = yaml.safe_load(fichier)["rules"]

    # Les étapes dans l'ordre : la sortie de chacune est l'entrée de la suivante.
    df = preparer_employes(projet / "input" / "employes.csv",
                           projet / "input" / "bands.csv",
                           projet / "input" / "market.csv")
    gg = gender_gap_analysis(df)
    df = former_cohortes(df, rule_params)
    df = apply_rulebook(df, rule_params)
    df = ml_anomaly(df, rule_params)
    df = apply_ml_strong_signal(df, rule_params)
    df = aggregate_risk(df, rule_params)
    df = recommendations(df, rule_params)

    sortie = generate_dashboard(df, gg, projet / "output" / "dashboard")
    print(f"Tableau de bord enregistré dans : {sortie}")
