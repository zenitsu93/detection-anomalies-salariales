#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Génère un dashboard HTML interactif (graphiques Chart.js : hover, tooltips, légende
cliquable, animations) à partir des résultats de détection des anomalies salariales.

Deux façons de l'utiliser :
- En pipeline : detect_salary_anomalies_custom_fixed.py appelle generate_dashboard(df=...,
  gg=...) directement avec les DataFrames déjà calculés (pas de relecture disque).
- En standalone : `python src/generate_dashboard_html.py` relit anomalies.csv et
  gender_gap.csv dans output/principal/, pour régénérer le dashboard sans refaire tourner
  toute la détection.

Le calcul (agrégations, KPI) reste en Python / pandas ; seule la restitution visuelle est
déléguée à Chart.js (chargé depuis cdnjs), avec une mise en page CSS qui ne chevauche
jamais (contrairement aux graphiques natifs Excel, positionnés en coordonnées absolues).

Usage:
    python src/generate_dashboard_html.py
Produit : output/principal/dashboard_anomalies.html
"""

import json
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ANOMALIES_CSV = ROOT / "output" / "principal" / "anomalies.csv"
DEFAULT_GENDER_CSV = ROOT / "output" / "principal" / "gender_gap.csv"
DEFAULT_OUT_HTML = ROOT / "output" / "principal" / "dashboard_anomalies.html"

SEVERITY_ORDER = ["Critical", "Major", "Minor", "Info"]

CHARTJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.1/chart.umd.min.js"

# Même charte que l'outil Repères (decision_support/static/style.css) : la couleur porte un sens.
# Rouge → or pour la gravité ; ardoise pour les effectifs ; brun pour les montants.
STATUS = {
    "Critical": "#b3261e",
    "Major": "#d9731f",
    "Minor": "#e9a21b",
    "Info": "#c4c9cf",
}
SEVERITY_FR = {"Critical": "Critique", "Major": "Majeure", "Minor": "Mineure", "Info": "Info (sans action)"}
FLAG_FR = {
    "COMPA_RATIO": "Position dans la grille",
    "MARKET_GAP": "Écart au marché",
    "PEER_OUTLIER": "Écart aux collègues",
    "ML_STRONG_SIGNAL": "Signal statistique fort",
    "OUT_OF_BAND": "Hors grille",
}
SLATE = "#5b6b7d"
BROWN = "#4a2c1d"
GOLD = "#e9a21b"


def fmt_int(n):
    return f"{int(round(n)):,}".replace(",", " ")


def fmt_pct(x, decimals=1):
    return f"{x:.{decimals}f} %".replace(".", ",")


def _clean_numeric(series):
    """Convertit une colonne texte "449,30" (virgule décimale, éventuel séparateur de
    milliers) en nombre. Utilisé uniquement pour la lecture depuis anomalies.csv : les
    DataFrames reçus directement du pipeline de détection sont déjà numériques."""
    cleaned = (
        series.astype(str)
        .str.replace("\xa0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def load_data(anomalies_csv=None, gender_csv=None):
    """Relit les résultats depuis le disque (anomalies.csv encodé en UTF-8, séparateur
    virgule décimale). Utilisé pour régénérer le dashboard sans refaire tourner la
    détection ; le pipeline appelle generate_dashboard() directement avec les
    DataFrames en mémoire à la place."""
    anomalies_csv = Path(anomalies_csv) if anomalies_csv else DEFAULT_ANOMALIES_CSV
    gender_csv = Path(gender_csv) if gender_csv else DEFAULT_GENDER_CSV

    df = pd.read_csv(anomalies_csv, encoding="utf-8")
    num_cols = ["Fixe_Annuel_MAD", "Min", "Mid", "Max", "Market_Median", "Cout_Ajustement"]
    for c in num_cols:
        if c in df.columns:
            df[c] = _clean_numeric(df[c])

    if gender_csv.exists():
        gg = pd.read_csv(gender_csv, encoding="utf-8")
    else:
        gg = pd.DataFrame(columns=["Job_Family", "Grade", "Median_F", "Median_M", "M_div_F"])
    return df, gg


def build_aggregates(df: pd.DataFrame, gg: pd.DataFrame):
    aggs = {}

    # 1. Répartition par sévérité (toutes catégories, même à 0, pour une échelle stable)
    counts = df["Severity"].value_counts()
    aggs["severity"] = pd.DataFrame({
        "Severity": SEVERITY_ORDER,
        "Count": [int(counts.get(s, 0)) for s in SEVERITY_ORDER],
    })

    # 2. Anomalies par pôle (Entite_N1) x sévérité
    pivot = pd.crosstab(df["Entite_N1"], df["Severity"])
    for s in SEVERITY_ORDER:
        if s not in pivot.columns:
            pivot[s] = 0
    pivot = pivot[SEVERITY_ORDER]
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
    aggs["entite_severity"] = pivot.reset_index()

    # 3. Top 10 métiers (Job_Family) par nombre d'anomalies actionnables (Critical+Major+Minor)
    actionable = df[df["Severity"].isin(["Critical", "Major", "Minor"])]
    top_jobfam = (
        actionable.groupby("Job_Family").size().sort_values(ascending=False).head(10)
        .reset_index(name="Nb_Anomalies")
    )
    aggs["job_family"] = top_jobfam

    # 4. Coût d'ajustement total par pôle
    cost_by_entite = (
        df.groupby("Entite_N1")["Cout_Ajustement"].sum().sort_values(ascending=False)
        .reset_index()
    )
    aggs["cost_entite"] = cost_by_entite

    # 5. Signaux déclencheurs (Rule_Flags éclatés)
    flags = df["Rule_Flags"].dropna().astype(str).str.split(";").explode()
    flags = flags[flags != ""]
    flag_counts = flags.value_counts().reset_index()
    flag_counts.columns = ["Flag", "Count"]
    aggs["flags"] = flag_counts

    # 6. Distribution du RiskScore (tranches de 10, bornes basses incluses)
    # Pourquoi fermées à gauche : la sévérité est attribuée par « score >= seuil bas » (30, 50, 70) ;
    # une tranche [20, 30) ne contient ainsi que des Info, [30, 40) que des Minor, etc.
    bins = list(range(0, 100, 10)) + [float("inf")]
    labels = [f"{b}-{b+10}" for b in range(0, 100, 10)]
    cats = pd.cut(df["RiskScore"], bins=bins, labels=labels, right=False)
    dist = cats.value_counts().reindex(labels).fillna(0).astype(int).reset_index()
    dist.columns = ["Tranche_RiskScore", "Count"]
    # Sévérité majoritaire de chaque tranche, lue dans les données (pas de seuil recopié ici).
    dominant = df.groupby(cats, observed=False)["Severity"].agg(lambda s: s.mode().iat[0] if len(s) else None)
    dist["Severity"] = pd.Series(dominant.reindex(labels).values).fillna("—").values
    aggs["riskscore_dist"] = dist

    # 7. Top 10 écarts de rémunération H/F les plus marqués (Job_Family x Grade)
    gg2 = gg.copy()
    if not gg2.empty and {"Job_Family", "Grade", "M_div_F"}.issubset(gg2.columns):
        gg2["Label"] = gg2["Job_Family"].astype(str) + " - Grade " + gg2["Grade"].astype(str)
        gg2["Ecart_pct"] = (gg2["M_div_F"] - 1.0) * 100.0
        gg2["Abs_Ecart"] = gg2["Ecart_pct"].abs()
        top_gap = gg2.sort_values("Abs_Ecart", ascending=False).head(10)[
            ["Label", "Job_Family", "Grade", "Median_F", "Median_M", "M_div_F", "Ecart_pct"]
        ].reset_index(drop=True)
    else:
        top_gap = pd.DataFrame(columns=["Label", "Job_Family", "Grade", "Median_F", "Median_M", "M_div_F", "Ecart_pct"])
    aggs["gender_gap_top"] = top_gap

    return aggs


def build_kpis(df, aggs):
    total_effectif = len(df)
    n_major = int((df["Severity"] == "Major").sum())
    n_critical = int((df["Severity"] == "Critical").sum())
    n_minor = int((df["Severity"] == "Minor").sum())
    n_info = int((df["Severity"] == "Info").sum())
    total_cost = float(df["Cout_Ajustement"].sum())
    return {
        "effectif_total": total_effectif,
        "n_critical": n_critical,
        "n_major": n_major,
        "n_minor": n_minor,
        "n_info": n_info,
        "pct_action": (n_critical + n_major + n_minor) / total_effectif * 100 if total_effectif else 0.0,
        "total_cost": total_cost,
    }


def build_data(df, gg):
    aggs = build_aggregates(df, gg)
    kpis = build_kpis(df, aggs)

    entite_sev = aggs["entite_severity"]
    sev_totals = aggs["severity"].set_index("Severity")["Count"].to_dict()
    # Pourquoi sans « Ensemble » ni « Info » : le total est déjà dans les indicateurs, et les Info
    # (aucune action) écrasaient l'échelle des anomalies à traiter.
    used_sev = [s for s in SEVERITY_ORDER if s != "Info" and sev_totals.get(s, 0) > 0] or SEVERITY_ORDER[:3]
    severity_chart = {
        "labels": entite_sev["Entite_N1"].tolist(),
        "datasets": [
            {"code": s, "label": SEVERITY_FR[s], "data": entite_sev[s].astype(int).tolist(),
             "backgroundColor": STATUS[s]}
            for s in used_sev
        ],
    }

    job = aggs["job_family"]
    job_chart = {"labels": job["Job_Family"].tolist(), "data": job["Nb_Anomalies"].astype(int).tolist()}

    cost = aggs["cost_entite"]
    cost_chart = {"labels": cost["Entite_N1"].tolist(), "data": [round(float(v), 1) for v in cost["Cout_Ajustement"]]}

    flags = aggs["flags"]
    flags_chart = {"labels": [FLAG_FR.get(f, f) for f in flags["Flag"]], "codes": flags["Flag"].tolist(),
                   "data": flags["Count"].astype(int).tolist()}

    rs = aggs["riskscore_dist"]
    bounds = [[b, b + 10] for b in range(0, 100, 10)][: len(rs)]
    riskscore_chart = {
        "labels": rs["Tranche_RiskScore"].tolist(),
        "data": rs["Count"].astype(int).tolist(),
        "colors": [STATUS.get(s, STATUS["Info"]) for s in rs["Severity"]],
        "bounds": bounds,
    }

    gap = aggs["gender_gap_top"]
    gap_vals = [round(float(v), 1) for v in gap["Ecart_pct"]]
    gap_chart = {
        "labels": gap["Label"].tolist(),
        "data": gap_vals,
        "colors": [SLATE if v > 0 else GOLD for v in gap_vals],
        "meta": [{"job_family": r["Job_Family"], "grade": int(r["Grade"])} for _, r in gap.iterrows()],
    }

    # Population individuelle (toutes les lignes), pour le clic-sur-graphe -> liste des
    # salariés concernés. Format compact (colonnes + lignes en tableau) plutôt qu'une liste
    # d'objets, pour ne pas répéter les noms de colonnes 10 000 fois dans le JSON.
    record_cols = [
        "Matricule", "Entite_N1", "Job_Family", "Job_Title", "Grade", "Severity",
        "RiskScore", "CompaRatio", "Rule_Flags", "Sexe", "Cout_Ajustement", "Reco",
    ]
    record_cols = [c for c in record_cols if c in df.columns]
    rec_df = df[record_cols].copy()
    for c in ("RiskScore", "CompaRatio", "Cout_Ajustement"):
        if c in rec_df.columns:
            rec_df[c] = rec_df[c].round(2)
    rec_df = rec_df.where(pd.notna(rec_df), None)
    records = {"cols": record_cols, "rows": rec_df.values.tolist()}

    return {
        "kpis": kpis,
        "severity": severity_chart,
        "job": job_chart,
        "cost": cost_chart,
        "flags": flags_chart,
        "riskscore": riskscore_chart,
        "gap": gap_chart,
        "records": records,
        "tables": {k: aggs[k].to_dict("records") for k in aggs},
    }


# Noms de colonnes lisibles, partagés par les tableaux détaillés et la liste des salariés.
COL_FR = {
    "Entite_N1": "Pôle", "Job_Family": "Métier", "Job_Title": "Poste", "Severity": "Sévérité",
    "Count": "Nombre", "Nb_Anomalies": "Anomalies", "Cout_Ajustement": "Coût d'ajustement",
    "Flag": "Signal", "Tranche_RiskScore": "Score de risque", "Label": "Métier × grade",
    "Median_F": "Médiane femmes", "Median_M": "Médiane hommes", "M_div_F": "Ratio H/F",
    "Ecart_pct": "Écart (%)", "RiskScore": "Score", "Rule_Flags": "Signaux", "Reco": "Recommandation",
    "Critical": "Critique", "Major": "Majeure", "Minor": "Mineure",
}


def table_html(rows):
    if not rows:
        return "<p>(aucune donnée)</p>"
    cols = list(rows[0].keys())
    head = "".join(f"<th>{escape(str(COL_FR.get(c, c)))}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(r[c]))}</td>" for c in cols) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_html(data):
    kpis = data["kpis"]
    # Un libellé contenant </script> doit rester du texte dans les données embarquées.
    data_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    names_json = json.dumps({"cols": COL_FR, "sev": SEVERITY_FR, "flags": FLAG_FR}, ensure_ascii=False).replace("<", "\\u003c")
    generated = datetime.now().strftime("%d/%m/%Y à %H:%M")
    n_action = kpis["n_critical"] + kpis["n_major"] + kpis["n_minor"]

    tables_html = "".join(
        f'<details class="data-toggle"><summary>{title}</summary><div class="table-wrap">{table_html(rows)}</div></details>'
        for title, rows in [
            ("Répartition par sévérité", data["tables"]["severity"]),
            ("Anomalies par pôle", data["tables"]["entite_severity"]),
            ("Top métiers", data["tables"]["job_family"]),
            ("Coût par pôle", data["tables"]["cost_entite"]),
            ("Signaux déclencheurs", data["tables"]["flags"]),
            ("Distribution du score de risque", data["tables"]["riskscore_dist"]),
            ("Écarts de rémunération H/F", data["tables"]["gender_gap_top"]),
        ]
    )

    # Pourquoi doctype, lang et charset : sans eux, le navigateur passait en mode dégradé et pouvait
    # deviner un mauvais encodage (accents cassés) à l'ouverture du fichier ; viewport pour le mobile.
    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repères — Anomalies salariales</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='3' fill='%23e9a21b'/%3E%3Crect x='9' y='9' width='14' height='14' fill='%23fff'/%3E%3Crect x='15' y='4' width='2' height='24' fill='%234a2c1d'/%3E%3C/svg%3E">
<script src="{CHARTJS_URL}"></script>
<style>
/* Même charte que l'outil Repères (decision_support/static/style.css). */
:root {{
  --brand: {GOLD}; --brand-soft: #fdf3dc; --brand-dark: {BROWN};
  --bg: #f3f4f6; --panel: #fff; --panel-head: #fafafa;
  --ink: #1f2328; --muted: #5f6670; --faint: #8b929b;
  --line: #dde0e4; --line-soft: #eceef1; --critical: {STATUS['Critical']};
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

.kpis {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 16px; border-left: 4px solid var(--brand); }}
.kpis div {{ padding: 16px 20px; }}
.kpis div + div {{ border-left: 1px solid var(--line-soft); }}
.kpis dt {{ font-size: 12px; color: var(--muted); }}
.kpis dd {{ margin: 2px 0 0; font-size: 24px; font-weight: 600; white-space: nowrap; }}
.kpis dd small {{ display: block; font-size: 12px; font-weight: 400; color: var(--faint); }}
.kpis .sev {{ display: inline-block; width: 8px; height: 8px; margin-right: 6px; vertical-align: 2px; }}
.kpis .critical {{ color: var(--critical); }}

.grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin-bottom: 16px; }}
.full {{ grid-column: 1 / -1; }}
.chart-box {{ position: relative; width: 100%; }}
.h-sm {{ height: 240px; }}
.h-md {{ height: 300px; }}
.h-lg {{ height: 360px; }}

details.data-toggle {{ border-top: 1px solid var(--line-soft); }}
details.data-toggle:first-child {{ border-top: 0; }}
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
.overlay .panel {{ width: 100%; max-width: 1000px; max-height: 88vh; display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,.2); }}
.overlay .panel-head {{ padding: 12px 16px; }}
.overlay h3 {{ font-size: 15px; font-weight: 600; }}
.overlay .sub {{ font-size: 12px; color: var(--muted); }}
.overlay .panel-body {{ overflow: auto; padding: 0; }}
.overlay th {{ position: sticky; top: 0; }}
.head-actions {{ display: flex; gap: 8px; flex: none; }}
button {{ font: 500 13px var(--font); height: 32px; padding: 0 12px; background: var(--panel); color: var(--ink);
  border: 1px solid #c4c9cf; border-radius: var(--radius); cursor: pointer; }}
button:hover {{ background: var(--panel-head); border-color: var(--faint); }}
button:focus-visible, summary:focus-visible {{ outline: 2px solid var(--brand); outline-offset: 2px; }}
.sev-tag {{ display: inline-block; padding: 0 6px; border-radius: 2px; font-size: 12px; font-weight: 600; }}

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
    <div><dt>Effectif analysé</dt><dd>{fmt_int(kpis['effectif_total'])} salariés</dd></div>
    <div><dt>Montants</dt><dd>Unité source</dd></div>
    <div><dt>Généré le</dt><dd>{generated}</dd></div>
  </dl>
</header>
<main>
  <div class="page-head">
    <div><p class="crumb">Rémunération › Anomalies</p><h1>Tableau de bord des anomalies</h1></div>
    <p class="page-hint">Cliquez une barre pour afficher les salariés concernés.</p>
  </div>

  <dl class="panel kpis">
    <div><dt>À traiter</dt><dd>{fmt_pct(kpis['pct_action'])}<small>{fmt_int(n_action)} salariés</small></dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Critical']}"></span>Critiques</dt><dd class="critical">{fmt_int(kpis['n_critical'])}</dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Major']}"></span>Majeures</dt><dd>{fmt_int(kpis['n_major'])}</dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Minor']}"></span>Mineures</dt><dd>{fmt_int(kpis['n_minor'])}</dd></div>
    <div><dt>Coût d'ajustement total</dt><dd>{fmt_int(kpis['total_cost'])}<small>unité source</small></dd></div>
  </dl>

  <div class="grid">
    <section class="panel full">
      <div class="panel-head"><h2 class="panel-title">Anomalies à traiter par pôle</h2><span class="panel-unit">salariés</span></div>
      <div class="panel-body"><div class="chart-box h-sm"><canvas id="chart-severity"></canvas></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Top 10 métiers concernés</h2><span class="panel-unit">anomalies à traiter</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-job"></canvas></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Coût d'ajustement par pôle</h2><span class="panel-unit">unité source</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-cost"></canvas></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Signaux déclencheurs</h2><span class="panel-unit">salariés</span></div>
      <div class="panel-body"><div class="chart-box h-md"><canvas id="chart-flags"></canvas></div>
        <p class="note">Un salarié peut déclencher plusieurs signaux.</p></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Score de risque</h2><span class="panel-unit">salariés par tranche</span></div>
      <div class="panel-body"><div class="chart-box h-md"><canvas id="chart-risk"></canvas></div>
        <p class="note">Couleur : sévérité attribuée aux salariés de la tranche.</p></div>
    </section>
    <section class="panel full">
      <div class="panel-head"><h2 class="panel-title">Écarts hommes / femmes les plus marqués</h2><span class="panel-unit">métier × grade</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-gap"></canvas></div>
        <p class="note">Écart entre salaires médians. Ardoise : hommes mieux payés ; or : femmes mieux payées.</p></div>
    </section>
    <details class="panel full data-panel">
      <summary class="panel-head"><h2 class="panel-title">Données détaillées</h2><span class="panel-unit">afficher</span></summary>
      {tables_html}
    </details>
  </div>

  <footer>Restitution des résultats du moteur de détection (anomalies.csv, gender_gap.csv), sans recalcul.</footer>
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

// ---- Panneau "population concernée" (clic sur un graphe) --------------------------
const RCOLS = DATA.records.cols;
const RIDX = {{}};
RCOLS.forEach((c, i) => RIDX[c] = i);
const RROWS = DATA.records.rows;
const MAX_ROWS_SHOWN = 300;
const NUM = new Intl.NumberFormat('fr-FR', {{ maximumFractionDigits: 2 }});

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
  if (col === 'Severity') return '<td><span class="sev-tag" style="background:' + (STATUS[v] || '#eee') + '22;color:' + (STATUS[v] || '#555') + '">' + escapeText(NAMES.sev[v] || v) + '</span></td>';
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
    const shown = matches.slice(0, MAX_ROWS_SHOWN);
    const head = RCOLS.map(c => '<th>' + escapeText(NAMES.cols[c] || c) + '</th>').join('');
    const body = shown.map(r => '<tr>' + r.map((v, i) => cellHtml(RCOLS[i], v)).join('') + '</tr>').join('');
    panelBody.innerHTML = '<table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table>';
  }}
  overlay.hidden = false;
}}

// Export de la sélection complète : séparateur « ; » et BOM pour une ouverture directe dans Excel (fr).
document.getElementById('panel-export').addEventListener('click', () => {{
  const q = v => {{ const s = v === null || v === undefined ? '' : String(v); return /[";\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }};
  const lines = [RCOLS.map(c => q(NAMES.cols[c] || c)).join(';')]
    .concat(lastMatches.map(r => r.map(v => q(typeof v === 'number' ? String(v).replace('.', ',') : v)).join(';')));
  const url = URL.createObjectURL(new Blob(['\\ufeff' + lines.join('\\r\\n')], {{ type: 'text/csv;charset=utf-8' }}));
  const a = document.createElement('a'); a.href = url;
  a.download = 'salaries_' + lastTitle.normalize('NFD').replace(/[^\\w]+/g, '_').replace(/^_|_$/g, '').toLowerCase() + '.csv';
  a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}});

// Pourquoi une fusion profonde : Object.assign remplaçait tout le bloc « plugins » dès qu'un
// graphique ajoutait une infobulle, ce qui réaffichait la légende avec le libellé « undefined ».
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
    // Pourquoi : sans locale, Chart.js affichait « 70,000 » (format anglais) au lieu de « 70 000 ».
    locale: 'fr-FR',
    responsive: true,
    maintainAspectRatio: false,
    animation: {{ duration: 400 }},
    onHover: (evt, els) => {{ evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; }},
    plugins: {{
      legend: {{ display: false, position: 'top', align: 'start', labels: {{ boxWidth: 10, boxHeight: 10, padding: 16 }} }},
      tooltip: {{ backgroundColor: '#1f2328', padding: 10, cornerRadius: 3, displayColors: false }},
    }},
    scales: {{
      x: {{ grid: {{ color: GRID }}, border: {{ display: false }} }},
      y: {{ grid: {{ color: GRID }}, border: {{ display: false }} }},
    }},
  }}, extra);
}}
// Libellés d'axe raccourcis sur petit écran : Chart.js les coupait sinon au bord du graphique.
const shortTicks = {{ callback(v) {{ const l = this.getLabelForValue(v); return innerWidth < 600 && l.length > 16 ? l.slice(0, 15) + '…' : l; }} }};
const hbar = (color, extra) => merge({{ backgroundColor: color, borderRadius: 2, maxBarThickness: 18 }}, extra || {{}});
const pick = (els, fn) => {{ if (els.length) fn(els[0].index, els[0].datasetIndex); }};

new Chart(document.getElementById('chart-severity'), {{
  type: 'bar',
  data: {{ labels: DATA.severity.labels, datasets: DATA.severity.datasets.map(d => hbar(d.backgroundColor, {{ label: d.label, data: d.data }})) }},
  options: baseOptions({{
    indexAxis: 'y',
    plugins: {{ legend: {{ display: true }}, tooltip: {{ displayColors: true }} }},
    scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, grid: {{ display: false }} }} }},
    onClick: (evt, els) => pick(els, (i, d) => {{
      const pole = DATA.severity.labels[i], sev = DATA.severity.datasets[d];
      showPopulation(pole + ' — ' + sev.label, r => r[RIDX.Entite_N1] === pole && r[RIDX.Severity] === sev.code);
    }}),
  }}),
}});

new Chart(document.getElementById('chart-job'), {{
  type: 'bar',
  data: {{ labels: DATA.job.labels, datasets: [hbar('{SLATE}', {{ data: DATA.job.data }})] }},
  options: baseOptions({{
    indexAxis: 'y', scales: {{ y: {{ grid: {{ display: false }}, ticks: shortTicks }} }},
    onClick: (evt, els) => pick(els, i => {{
      const label = DATA.job.labels[i];
      showPopulation('Métier : ' + label, r => r[RIDX.Job_Family] === label && r[RIDX.Severity] !== 'Info');
    }}),
  }}),
}});

new Chart(document.getElementById('chart-cost'), {{
  type: 'bar',
  data: {{ labels: DATA.cost.labels, datasets: [hbar('{BROWN}', {{ data: DATA.cost.data }})] }},
  options: baseOptions({{
    indexAxis: 'y', scales: {{ y: {{ grid: {{ display: false }}, ticks: shortTicks }} }},
    onClick: (evt, els) => pick(els, i => {{
      const label = DATA.cost.labels[i];
      showPopulation("Coût d'ajustement : " + label, r => r[RIDX.Entite_N1] === label && r[RIDX.Cout_Ajustement] > 0);
    }}),
  }}),
}});

new Chart(document.getElementById('chart-flags'), {{
  type: 'bar',
  data: {{ labels: DATA.flags.labels, datasets: [hbar('{SLATE}', {{ data: DATA.flags.data }})] }},
  options: baseOptions({{
    indexAxis: 'y', scales: {{ y: {{ grid: {{ display: false }}, ticks: shortTicks }} }},
    plugins: {{ tooltip: {{ callbacks: {{ title: items => items[0].label + ' (' + DATA.flags.codes[items[0].dataIndex] + ')' }} }} }},
    onClick: (evt, els) => pick(els, i => {{
      const code = DATA.flags.codes[i];
      showPopulation('Signal : ' + DATA.flags.labels[i], r => (r[RIDX.Rule_Flags] || '').split(';').includes(code));
    }}),
  }}),
}});

new Chart(document.getElementById('chart-risk'), {{
  type: 'bar',
  data: {{ labels: DATA.riskscore.labels, datasets: [{{ data: DATA.riskscore.data, backgroundColor: DATA.riskscore.colors, borderRadius: 2, maxBarThickness: 40 }}] }},
  options: baseOptions({{
    scales: {{ x: {{ grid: {{ display: false }} }} }},
    onClick: (evt, els) => pick(els, i => {{
      const [lo, hi] = DATA.riskscore.bounds[i], last = i === DATA.riskscore.bounds.length - 1;
      showPopulation('Score de risque ' + DATA.riskscore.labels[i], r => r[RIDX.RiskScore] >= lo && (last || r[RIDX.RiskScore] < hi));
    }}),
  }}),
}});

new Chart(document.getElementById('chart-gap'), {{
  type: 'bar',
  data: {{ labels: DATA.gap.labels, datasets: [hbar(DATA.gap.colors, {{ data: DATA.gap.data }})] }},
  options: baseOptions({{
    indexAxis: 'y',
    plugins: {{ tooltip: {{ callbacks: {{ label: c => (c.parsed.x > 0 ? '+' : '') + NUM.format(c.parsed.x) + ' %' }} }} }},
    scales: {{ x: {{ ticks: {{ callback: v => (v > 0 ? '+' : '') + v + ' %' }} }}, y: {{ grid: {{ display: false }}, ticks: shortTicks }} }},
    onClick: (evt, els) => pick(els, i => {{
      const meta = DATA.gap.meta[i];
      showPopulation(DATA.gap.labels[i], r => r[RIDX.Job_Family] === meta.job_family && r[RIDX.Grade] === meta.grade);
    }}),
  }}),
}});
</script>
</body>
</html>
"""
    return html


def generate_dashboard(df=None, gg=None, anomalies_csv=None, gender_csv=None, out_html=None):
    """Génère le dashboard HTML et l'écrit sur disque.

    Appelé par le pipeline de détection avec `df`/`gg` déjà en mémoire (pas de
    relecture disque). En standalone (aucun argument), relit anomalies.csv et
    gender_gap.csv dans output/principal/.
    """
    if df is None or gg is None:
        df, gg = load_data(anomalies_csv, gender_csv)
    data = build_data(df, gg)
    html = build_html(data)
    out_path = Path(out_html) if out_html else DEFAULT_OUT_HTML
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main():
    out_path = generate_dashboard()
    print(f"Dashboard genere : {out_path}")


if __name__ == "__main__":
    main()
