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
from html import escape
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ANOMALIES_CSV = ROOT / "output" / "principal" / "anomalies.csv"
DEFAULT_GENDER_CSV = ROOT / "output" / "principal" / "gender_gap.csv"
DEFAULT_OUT_HTML = ROOT / "output" / "principal" / "dashboard_anomalies.html"

SEVERITY_ORDER = ["Critical", "Major", "Minor", "Info"]

CHARTJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.1/chart.umd.min.js"

# Couleurs reprises du palette de référence du skill dataviz (references/palette.md) :
# statuts (Critical/Major/Minor/Info), rampe séquentielle bleue, et deux teintes
# catégorielles (bleu / magenta) pour l'écart hommes-femmes.
STATUS = {
    "Critical": "#d03b3b",
    "Major": "#ec835a",
    "Minor": "#fab219",
    "Info": "#0ca30c",
}
SEQ_BLUE = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
            "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
MAGENTA = "#e87ba4"


def fmt_int(n):
    return f"{int(round(n)):,}".replace(",", " ")


def fmt_pct(x, decimals=1):
    return f"{x:.{decimals}f}%".replace(".", ",")


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

    # 6. Distribution du RiskScore (tranches de 10)
    bins = list(range(0, 101, 10))
    labels = [f"{b}-{b+10}" for b in bins[:-1]]
    cats = pd.cut(df["RiskScore"], bins=bins, labels=labels, include_lowest=True, right=True)
    dist = cats.value_counts().reindex(labels).fillna(0).astype(int).reset_index()
    dist.columns = ["Tranche_RiskScore", "Count"]
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
    used_sev = [s for s in SEVERITY_ORDER if sev_totals.get(s, 0) > 0]
    if not used_sev:
        used_sev = SEVERITY_ORDER
    severity_chart = {
        "labels": ["Ensemble"] + entite_sev["Entite_N1"].tolist(),
        "datasets": [
            {
                "label": s,
                "data": [int(sev_totals.get(s, 0))] + entite_sev[s].astype(int).tolist(),
                "backgroundColor": STATUS[s],
            }
            for s in used_sev
        ],
    }

    job = aggs["job_family"]
    job_chart = {"labels": job["Job_Family"].tolist(), "data": job["Nb_Anomalies"].astype(int).tolist()}

    cost = aggs["cost_entite"]
    cost_chart = {"labels": cost["Entite_N1"].tolist(), "data": [round(float(v), 1) for v in cost["Cout_Ajustement"]]}

    flags = aggs["flags"]
    flags_chart = {"labels": flags["Flag"].tolist(), "data": flags["Count"].astype(int).tolist()}

    rs = aggs["riskscore_dist"]
    bounds = [[b, b + 10] for b in range(0, 100, 10)][: len(rs)]
    riskscore_chart = {
        "labels": rs["Tranche_RiskScore"].tolist(),
        "data": rs["Count"].astype(int).tolist(),
        "colors": SEQ_BLUE[: len(rs)],
        "bounds": bounds,
    }

    gap = aggs["gender_gap_top"]
    gap_vals = [round(float(v), 1) for v in gap["Ecart_pct"]]
    gap_chart = {
        "labels": gap["Label"].tolist(),
        "data": gap_vals,
        "colors": [BLUE if v > 0 else MAGENTA for v in gap_vals],
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


def table_html(rows):
    if not rows:
        return "<p>(aucune donnée)</p>"
    cols = list(rows[0].keys())
    head = "".join(f"<th>{escape(str(c))}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(r[c]))}</td>" for c in cols) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_html(data):
    kpis = data["kpis"]
    # Un libellé contenant </script> doit rester du texte dans les données embarquées.
    data_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    tables_html = "".join(
        f'<details class="data-toggle"><summary>{title}</summary>{table_html(rows)}</details>'
        for title, rows in [
            ("Répartition par sévérité", data["tables"]["severity"]),
            ("Anomalies par pôle", data["tables"]["entite_severity"]),
            ("Top métiers", data["tables"]["job_family"]),
            ("Coût par pôle", data["tables"]["cost_entite"]),
            ("Signaux déclencheurs", data["tables"]["flags"]),
            ("Distribution RiskScore", data["tables"]["riskscore_dist"]),
            ("Écarts de rémunération H/F", data["tables"]["gender_gap_top"]),
        ]
    )

    html = f"""<title>Anomalies Salariales</title>
<script src="{CHARTJS_URL}"></script>
<style>
:root {{
  color-scheme: light;
  --page-bg: #f9f9f7;
  --surface-1: #fcfcfb;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --gridline: #e1e0d9;
  --border: rgba(11,11,11,0.10);
}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) {{
    color-scheme: dark;
    --page-bg: #0d0d0d;
    --surface-1: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --gridline: #2c2c2a;
    --border: rgba(255,255,255,0.10);
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --page-bg: #0d0d0d;
  --surface-1: #1a1a19;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #898781;
  --gridline: #2c2c2a;
  --border: rgba(255,255,255,0.10);
}}

* {{ box-sizing: border-box; }}
body {{
  background: var(--page-bg);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 20px 16px 48px;
  max-width: 1200px;
  margin: 0 auto;
}}
header h1 {{ font-size: 22px; margin: 0 0 4px; }}
header p {{ color: var(--text-secondary); margin: 0 0 24px; font-size: 14px; }}

.kpi-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 28px; }}
.kpi-tile {{
  flex: 1 1 150px; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px;
}}
.kpi-tile .value {{ font-size: 24px; font-weight: 600; }}
.kpi-tile .label {{ font-size: 12px; color: var(--text-secondary); margin-top: 2px; }}

.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; margin-bottom: 16px; }}
.card {{
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
  padding: 18px 20px; min-width: 0;
}}
.card.full {{ grid-column: 1 / -1; }}
.card h2 {{ font-size: 15px; margin: 0 0 14px; }}
.card .note {{ font-size: 12px; color: var(--text-muted); margin-top: 10px; }}
.chart-box {{ position: relative; width: 100%; }}
.h-sm {{ height: 220px; }}
.h-md {{ height: 300px; }}
.h-lg {{ height: 380px; }}

details.data-toggle {{ margin: 6px 0; font-size: 12px; }}
details.data-toggle summary {{ cursor: pointer; color: var(--text-secondary); padding: 6px 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin: 6px 0 14px; }}
th, td {{ text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--gridline); white-space: nowrap; }}
th {{ color: var(--text-muted); font-weight: 600; }}
td {{ font-variant-numeric: tabular-nums; }}

.card .hint {{ font-size: 11px; color: var(--text-muted); margin-top: 8px; }}

.overlay {{
  position: fixed; inset: 0; background: rgba(0,0,0,0.45);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 5vh 16px; z-index: 50;
}}
.overlay[hidden] {{ display: none; }}
.panel {{
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
  width: 100%; max-width: 900px; max-height: 88vh; display: flex; flex-direction: column;
  box-shadow: 0 12px 40px rgba(0,0,0,0.25);
}}
.panel-head {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--gridline);
}}
.panel-head h3 {{ margin: 0; font-size: 15px; }}
.panel-head .sub {{ font-size: 12px; color: var(--text-muted); margin-top: 2px; }}
.panel-close {{
  background: none; border: 1px solid var(--border); color: var(--text-secondary);
  border-radius: 6px; width: 28px; height: 28px; cursor: pointer; font-size: 14px; flex: 0 0 auto;
}}
.panel-body {{ overflow: auto; padding: 8px 20px 20px; }}
.panel-body table {{ margin: 0; }}
.panel-body th {{ position: sticky; top: 0; background: var(--surface-1); }}

footer {{ margin-top: 32px; font-size: 11px; color: var(--text-muted); }}
</style>

<header>
  <h1>Détection des anomalies salariales — Tableau de bord</h1>
  <p>{fmt_int(kpis['effectif_total'])} salariés analysés — {fmt_int(kpis['n_critical'] + kpis['n_major'])} anomalies Critical/Major, {fmt_int(kpis['n_minor'])} Minor</p>
</header>

<div class="kpi-row">
  <div class="kpi-tile"><div class="value">{fmt_int(kpis['effectif_total'])}</div><div class="label">Effectif analysé</div></div>
  <div class="kpi-tile"><div class="value">{fmt_int(kpis['n_critical'])}</div><div class="label">Anomalies Critical</div></div>
  <div class="kpi-tile"><div class="value">{fmt_int(kpis['n_major'])}</div><div class="label">Anomalies Major</div></div>
  <div class="kpi-tile"><div class="value">{fmt_int(kpis['n_minor'])}</div><div class="label">Anomalies Minor</div></div>
  <div class="kpi-tile"><div class="value">{fmt_pct(kpis['pct_action'])}</div><div class="label">% effectif à traiter</div></div>
  <div class="kpi-tile"><div class="value">{fmt_int(kpis['total_cost'])}</div><div class="label">Coût d'ajustement total (unité source)</div></div>
</div>

<div class="grid">
  <div class="card full">
    <h2>Répartition des anomalies par sévérité et par pôle</h2>
    <div class="chart-box h-md"><canvas id="chart-severity"></canvas></div>
    <div class="note">{fmt_int(kpis['n_critical'])} anomalie(s) « Critical » sur cet effectif. Cliquez sur la légende pour isoler une sévérité.</div>
    <div class="hint">Cliquez une barre pour voir la liste des salariés concernés.</div>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>Top 10 métiers les plus concernés par une anomalie</h2>
    <div class="chart-box h-lg"><canvas id="chart-job"></canvas></div>
    <div class="hint">Cliquez une barre pour voir la liste des salariés concernés.</div>
  </div>
  <div class="card">
    <h2>Coût d'ajustement recommandé par pôle (unité source)</h2>
    <div class="chart-box h-lg"><canvas id="chart-cost"></canvas></div>
    <div class="hint">Cliquez une barre pour voir la liste des salariés concernés.</div>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>Signaux déclencheurs les plus fréquents</h2>
    <div class="chart-box h-md"><canvas id="chart-flags"></canvas></div>
    <div class="hint">Cliquez une barre pour voir la liste des salariés concernés.</div>
  </div>
  <div class="card">
    <h2>Distribution du score de risque (RiskScore)</h2>
    <div class="chart-box h-md"><canvas id="chart-risk"></canvas></div>
    <div class="hint">Cliquez une barre pour voir la liste des salariés concernés.</div>
  </div>
</div>

<div class="grid">
  <div class="card full">
    <h2>Top 10 écarts de rémunération Hommes/Femmes (métier x grade)</h2>
    <div class="chart-box h-lg"><canvas id="chart-gap"></canvas></div>
    <div class="note">Écart en % du salaire médian de l'autre sexe, sur la combinaison métier × grade. Bleu = hommes mieux payés, magenta = femmes mieux payées.</div>
    <div class="hint">Cliquez une barre pour voir la population du métier × grade concerné.</div>
  </div>
</div>

<div class="grid">
  <div class="card full">
    <h2>Données détaillées (vue table)</h2>
    {tables_html}
  </div>
</div>

<footer>Généré automatiquement à partir de anomalies.csv et gender_gap.csv — aucun recalcul, restitution des résultats du moteur de détection.</footer>

<div class="overlay" id="panel-overlay" hidden>
  <div class="panel">
    <div class="panel-head">
      <div>
        <h3 id="panel-title">—</h3>
        <div class="sub" id="panel-sub"></div>
      </div>
      <button class="panel-close" id="panel-close" aria-label="Fermer">✕</button>
    </div>
    <div class="panel-body" id="panel-body"></div>
  </div>
</div>

<script>
const DATA = {data_json};

// ---- Panneau "population concernée" (clic sur un graphe) --------------------------
const RCOLS = DATA.records.cols;
const RIDX = {{}};
RCOLS.forEach((c, i) => RIDX[c] = i);
const RROWS = DATA.records.rows;
const MAX_ROWS_SHOWN = 300;

const overlay = document.getElementById('panel-overlay');
const panelTitle = document.getElementById('panel-title');
const panelSub = document.getElementById('panel-sub');
const panelBody = document.getElementById('panel-body');
document.getElementById('panel-close').addEventListener('click', closePanel);
overlay.addEventListener('click', e => {{ if (e.target === overlay) closePanel(); }});
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closePanel(); }});

function closePanel() {{ overlay.hidden = true; }}

function escapeText(value) {{
  const cell = document.createElement('span');
  cell.textContent = value === null ? '' : String(value);
  return cell.innerHTML;
}}

function showPopulation(title, predicate) {{
  const matches = RROWS.filter(predicate);
  panelTitle.textContent = title;
  panelSub.textContent = matches.length + ' salarié(s) concerné(s)'
    + (matches.length > MAX_ROWS_SHOWN ? ' — ' + MAX_ROWS_SHOWN + ' premiers affichés' : '');
  if (!matches.length) {{
    panelBody.innerHTML = '<p>Aucun salarié ne correspond à cette sélection.</p>';
  }} else {{
    const shown = matches.slice(0, MAX_ROWS_SHOWN);
    const head = RCOLS.map(c => '<th>' + escapeText(c) + '</th>').join('');
    const body = shown.map(r => '<tr>' + r.map(v => '<td>' + escapeText(v) + '</td>').join('') + '</tr>').join('');
    panelBody.innerHTML = '<table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table>';
  }}
  overlay.hidden = false;
}}

function themeColors() {{
  const cs = getComputedStyle(document.documentElement);
  return {{
    text: cs.getPropertyValue('--text-secondary').trim(),
    grid: cs.getPropertyValue('--gridline').trim(),
  }};
}}

function baseOptions(extra) {{
  const t = themeColors();
  Chart.defaults.color = t.text;
  Chart.defaults.font.family = "system-ui, -apple-system, 'Segoe UI', sans-serif";
  Chart.defaults.font.size = 12;
  const opts = {{
    responsive: true,
    maintainAspectRatio: false,
    animation: {{ duration: 500, easing: 'easeOutQuart' }},
    onHover: (evt, els) => {{ evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; }},
    plugins: {{
      legend: {{ display: false, labels: {{ boxWidth: 10, usePointStyle: true }} }},
      tooltip: {{
        backgroundColor: t.text, titleColor: '#fff', bodyColor: '#fff',
        padding: 10, cornerRadius: 6, displayColors: true,
      }},
    }},
    scales: {{
      x: {{ grid: {{ color: t.grid }}, ticks: {{ color: t.text }} }},
      y: {{ grid: {{ color: t.grid }}, ticks: {{ color: t.text }} }},
    }},
  }};
  return Object.assign(opts, extra);
}}

new Chart(document.getElementById('chart-severity'), {{
  type: 'bar',
  data: {{
    labels: DATA.severity.labels,
    datasets: DATA.severity.datasets.map(d => ({{
      label: d.label, data: d.data, backgroundColor: d.backgroundColor,
      borderRadius: 4, maxBarThickness: 24,
    }})),
  }},
  options: baseOptions({{
    indexAxis: 'y',
    plugins: {{ legend: {{ display: true, position: 'top' }}, tooltip: {{}} }},
    scales: {{ x: {{ stacked: true, grid: {{ color: themeColors().grid }} }}, y: {{ stacked: true, grid: {{ display: false }} }} }},
    onClick: (evt, els, chart) => {{
      if (!els.length) return;
      const el = els[0];
      const pole = DATA.severity.labels[el.index];
      const sev = chart.data.datasets[el.datasetIndex].label;
      const title = pole === 'Ensemble' ? 'Sévérité : ' + sev : pole + ' — ' + sev;
      const pred = pole === 'Ensemble'
        ? r => r[RIDX.Severity] === sev
        : r => r[RIDX.Entite_N1] === pole && r[RIDX.Severity] === sev;
      showPopulation(title, pred);
    }},
  }}),
}});

new Chart(document.getElementById('chart-job'), {{
  type: 'bar',
  data: {{ labels: DATA.job.labels, datasets: [{{ data: DATA.job.data, backgroundColor: '{BLUE}', borderRadius: 4, maxBarThickness: 20 }}] }},
  options: baseOptions({{
    indexAxis: 'y', scales: {{ y: {{ grid: {{ display: false }} }} }},
    onClick: (evt, els) => {{
      if (!els.length) return;
      const label = DATA.job.labels[els[0].index];
      showPopulation('Métier : ' + label, r => r[RIDX.Job_Family] === label && r[RIDX.Severity] !== 'Info');
    }},
  }}),
}});

new Chart(document.getElementById('chart-cost'), {{
  type: 'bar',
  data: {{ labels: DATA.cost.labels, datasets: [{{ data: DATA.cost.data, backgroundColor: '{ORANGE}', borderRadius: 4, maxBarThickness: 48 }}] }},
  options: baseOptions({{
    plugins: {{ tooltip: {{ callbacks: {{ label: c => c.parsed.y.toLocaleString('fr-FR') + ' (unité source)' }} }} }},
    scales: {{ x: {{ grid: {{ display: false }} }} }},
    onClick: (evt, els) => {{
      if (!els.length) return;
      const label = DATA.cost.labels[els[0].index];
      showPopulation("Coût d'ajustement : " + label, r => r[RIDX.Entite_N1] === label && r[RIDX.Cout_Ajustement] > 0);
    }},
  }}),
}});

new Chart(document.getElementById('chart-flags'), {{
  type: 'bar',
  data: {{ labels: DATA.flags.labels, datasets: [{{ data: DATA.flags.data, backgroundColor: '{AQUA}', borderRadius: 4, maxBarThickness: 20 }}] }},
  options: baseOptions({{
    indexAxis: 'y', scales: {{ y: {{ grid: {{ display: false }} }} }},
    onClick: (evt, els) => {{
      if (!els.length) return;
      const label = DATA.flags.labels[els[0].index];
      showPopulation('Signal : ' + label, r => (r[RIDX.Rule_Flags] || '').split(';').includes(label));
    }},
  }}),
}});

new Chart(document.getElementById('chart-risk'), {{
  type: 'bar',
  data: {{ labels: DATA.riskscore.labels, datasets: [{{ data: DATA.riskscore.data, backgroundColor: DATA.riskscore.colors, borderRadius: 4, maxBarThickness: 40 }}] }},
  options: baseOptions({{
    scales: {{ x: {{ grid: {{ display: false }}, title: {{ display: true, text: 'Score de risque', color: themeColors().text }} }} }},
    onClick: (evt, els) => {{
      if (!els.length) return;
      const i = els[0].index;
      const [lo, hi] = DATA.riskscore.bounds[i];
      showPopulation('Score de risque ' + DATA.riskscore.labels[i], r => r[RIDX.RiskScore] > (lo === 0 ? -1 : lo) && r[RIDX.RiskScore] <= hi);
    }},
  }}),
}});

new Chart(document.getElementById('chart-gap'), {{
  type: 'bar',
  data: {{ labels: DATA.gap.labels, datasets: [{{ data: DATA.gap.data, backgroundColor: DATA.gap.colors, borderRadius: 4, maxBarThickness: 20 }}] }},
  options: baseOptions({{
    indexAxis: 'y',
    plugins: {{ tooltip: {{ callbacks: {{ label: c => (c.parsed.x > 0 ? '+' : '') + c.parsed.x + '%' }} }} }},
    scales: {{ x: {{ grid: {{ color: themeColors().grid }}, title: {{ display: true, text: 'Écart en % (positif = hommes mieux payés)', color: themeColors().text }} }}, y: {{ grid: {{ display: false }} }} }},
    onClick: (evt, els) => {{
      if (!els.length) return;
      const meta = DATA.gap.meta[els[0].index];
      showPopulation(DATA.gap.labels[els[0].index], r => r[RIDX.Job_Family] === meta.job_family && r[RIDX.Grade] === meta.grade);
    }},
  }}),
}});
</script>
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
