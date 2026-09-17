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
    """Première restitution autonome : graphiques agrégés et tables."""
    payload = json.dumps(data, ensure_ascii=False, default=str).replace("<", "\u003c")
    sections = "".join("<h2>" + escape(name) + "</h2>" + table_html(rows) for name, rows in data["tables"].items())
    return ('<!doctype html><html lang="fr"><meta charset="utf-8">'
            '<title>Anomalies salariales</title><h1>Anomalies salariales</h1>'
            '<div style="max-width:1000px"><canvas id="severity"></canvas><canvas id="job"></canvas></div>'
            + sections + '<script src="' + CHARTJS_URL + '"></script><script>const data='
            + payload + ';new Chart(document.getElementById("severity"),{type:"bar",data:data.severity});'
            + 'new Chart(document.getElementById("job"),{type:"bar",data:{labels:data.job.labels,datasets:[{label:"Anomalies",data:data.job.data}]}});</script></html>')


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
