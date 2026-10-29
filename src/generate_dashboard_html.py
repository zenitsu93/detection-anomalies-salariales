#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TABLEAU DE BORD HTML DES ANOMALIES
==================================

Ce fichier crée un tableau de bord HTML (graphiques Plotly, avec le même zoom et le même bouton
« Agrandir » que la page d'exploration de visualisation/) à partir de :
- df : le DataFrame des salariés rendu par anomaly_recommandations.py, avec le score général
  (RiskScore) et la priorité (Severity) ajoutés par anomaly_score_general.py ;
- gg : le tableau rendu par anomaly_ecarts_hommes_femmes.py ;
- rule_params : les réglages de config/rules.yaml, pour citer le seuil bas de la règle CompaRatio
  sous le coût d'ajustement.
Il ne recalcule rien : il compte et affiche. Un clic sur une barre, un point ou un nombre de priorité
affiche les salariés concernés, avec un export Excel. Chaque tableau se filtre et se trie comme dans
Excel : une recherche au-dessus, et un menu ▾ dans chaque en-tête de colonne.

Un salarié est « à traiter » si sa priorité est Critical, Major ou Minor : les « Info » n'ont rien à
faire.

Utilisation :
- depuis Python :
      from generate_dashboard_html import generate_dashboard
      generate_dashboard(df, gg, rule_params, "output/dashboard")
- en ligne de commande, depuis le dossier du projet :
      python src/generate_dashboard_html.py
  Le tableau de bord est enregistré dans output/dashboard/, sous un nom daté
  (dashboard_anomalies_AAAA-MM-JJ_HH-MM-SS.html), à ouvrir avec un navigateur. Chaque lancement
  ajoute un fichier sans effacer les précédents.
"""

import json
from datetime import datetime
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

# Plotly dessine les graphiques ; SheetJS écrit le fichier Excel de la liste des salariés directement
# dans le navigateur. Pourquoi recopiés DANS le tableau de bord, depuis visualisation/vendor/, au lieu
# d'être chargés depuis internet : le fichier s'ouvre sans connexion (comme la page d'exploration), et
# reste complet même envoyé seul par mail. Il pèse en échange environ 6 Mo de plus.
VENDOR = Path(__file__).resolve().parent.parent / "visualisation" / "vendor"

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

# Les montants des fichiers d'entrée sont en kMAD (238.34 = 238 340 MAD) : c'est l'unité affichée.
UNITE = "kMAD"

# Les deux recommandations qui coûtent, avec leur nom à l'écran et leur couleur : brun foncé pour la
# remise au Min, brun clair pour le rapprochement du Mid (deux bruns, puisque ce sont deux montants).
ACTIONS = {"Ajuster au MIN": ("Remise au Min", BROWN), "Ajuster vers MID": ("Rapprochement du Mid", "#b07d55")}

# Les étiquettes traduites pour l'écran ; le code d'origine reste visible dans l'infobulle.
FLAG_FR = {
    # Pourquoi « Sous la grille » et plus « Hors grille » : la règle ne signale plus les salaires
    # au-dessus du Max (décision du comité du 15/10/2026), seulement ceux sous le Min.
    "OUT_OF_BAND": "Sous la grille",
    "COMPA_RATIO": "Position dans la grille",
    "MARKET_GAP": "Écart au marché",
    "PEER_OUTLIER": "Écart aux collègues",
    "MIN_SALARY": "Sous le salaire minimum",
    "ML_STRONG_SIGNAL": "Signal statistique fort",
}
# Les colonnes de la liste des salariés (clic sur une barre), et leur nom affiché.
COL_FR = {
    "Matricule": "Matricule", "Entite_N1": "Pôle", "Job_Family": "Métier", "Job_Title": "Poste",
    "Niveau": "Niveau", "Sexe": "Sexe", "Severity": "Priorité", "RiskScore": "Score général",
    "CompaRatio": "CompaRatio", "Rule_Flags": "Signaux",
    "Rule_Score": "Score de règles", "ML_AnomalyScore": "Score IA", "Reco": "Recommandation",
    "Cout_Ajustement": f"Coût d'ajustement ({UNITE})",
}


def fmt_int(n):
    return f"{int(round(n)):,}".replace(",", " ")


def fmt_num(x):
    """12345.6 -> « 12 345,6 » ; 5.0 -> « 5 »."""
    return f"{x:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")


def virgule(x):
    """0.85 -> « 0,85 »."""
    return f"{x:.2f}".replace(".", ",")


def build_data(df: pd.DataFrame, gg: pd.DataFrame, rule_params: dict) -> dict:
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
    # Le même coût, séparé selon l'action qui le crée, avec le nombre de salariés de chaque action.
    payant = df[df["Reco"].isin(list(ACTIONS))]
    cout_action = (payant.pivot_table(index="Entite_N1", columns="Reco", values="Cout_Ajustement", aggfunc="sum")
                   .reindex(index=cost.index, columns=list(ACTIONS)).fillna(0))
    nb_action = pd.crosstab(payant["Entite_N1"], payant["Reco"]).reindex(index=cost.index, columns=list(ACTIONS),
                                                                         fill_value=0)
    # Les trois scores comptés par tranches de 10 (tout ce qui dépasse 90 va dans la dernière). Même
    # arrondi et même calcul que la liste affichée au clic, pour que les deux comptes collent.
    scores = [{"code": col, "label": COL_FR[col], "color": couleur,
               "data": np.floor(df[col].round(2) / 10).clip(upper=9).astype(int)
                         .value_counts().reindex(range(10), fill_value=0).tolist()}
              for col, couleur in SCORE_COLORS.items()]
    # Tous les écarts hommes / femmes (le choix des 10 plus marqués ou d'un niveau se fait dans la page),
    # avec le nombre de femmes et d'hommes : un écart sur 3 personnes ne pèse pas comme un écart sur 300.
    # Un métier + niveau sans femme ou sans homme n'a pas d'écart : il est écarté.
    effectifs = df.groupby(["Job_Family", "Niveau", "Sexe"]).size().unstack(fill_value=0).reset_index()
    gap = gg.dropna(subset=["M_div_F"]).merge(effectifs, on=["Job_Family", "Niveau"])
    gap["Ecart_pct"] = (gap["M_div_F"] - 1) * 100
    gap = gap[["Job_Family", "Niveau", "Median_F", "Median_M", "F", "M", "Ecart_pct"]]
    gap = gap.round({"Median_F": 2, "Median_M": 2, "Ecart_pct": 1})

    # La liste des salariés : cases vides en None, sinon le JSON serait invalide.
    rec = df[list(COL_FR)].round(2)
    rec = rec.astype(object).where(rec.notna(), None)

    return {
        "kpis": {
            "effectif": len(df),
            "a_traiter": int(a_traiter.sum()),
            # Les quatre priorités, « Info » comprise : la rangée de chiffres clés a un compteur pour chacune.
            **{s: int((df["Severity"] == s).sum()) for s in SEVERITY_ORDER},
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
        "cost": {"labels": cost.index.tolist(), "data": cost.round(1).tolist(),
                 "datasets": [{"code": code, "label": nom, "color": couleur,
                               "data": cout_action[code].round(1).tolist(), "n": nb_action[code].astype(int).tolist()}
                              for code, (nom, couleur) in ACTIONS.items()],
                 # Le seuil bas de la règle CompaRatio, cité dans la note sous le graphique.
                 "seuil": virgule(rule_params["compa_ratio_low"])},
        "flags": {"labels": [FLAG_FR.get(f, f) for f in flags.index], "codes": flags.index.tolist(),
                  "data": flags.tolist()},
        "scores": {"labels": [f"{b}-{b + 10}" for b in range(0, 100, 10)], "datasets": scores},
        "gap": gap.to_dict("records"),
        "records": {"cols": list(COL_FR), "rows": rec.values.tolist()},
    }


def build_html(data: dict, maintenant: datetime) -> str:
    kpis = data["kpis"]
    # Un « < » dans un libellé ne doit pas pouvoir fermer la balise <script>.
    data_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    names_json = json.dumps({"cols": COL_FR, "flags": FLAG_FR, "sev": SEVERITY_FR}, ensure_ascii=False).replace("<", "\\u003c")
    # La même heure que dans le nom du fichier.
    generated = maintenant.strftime("%d/%m/%Y à %H:%M")
    pct = kpis["a_traiter"] / kpis["effectif"] * 100 if kpis["effectif"] else 0.0

    p, c = data["pole"], data["cost"]
    # Les tableaux des « Données détaillées » partent en JSON (titre, colonnes, lignes) et non plus en
    # HTML tout fait : la page les dessine elle-même, avec la même recherche et les mêmes filtres que la
    # liste des salariés. Pas de tableau des écarts hommes / femmes (le graphique par niveau le remplace)
    # ni du score général (ses trois courbes et leur infobulle donnent déjà les nombres).
    tables_json = json.dumps([
        {"title": titre, "cols": entetes, "rows": list(lignes)}
        for titre, entetes, lignes in [
            ("Anomalies à traiter par pôle", ["Pôle"] + [d["label"] for d in p["datasets"]],
             zip(p["labels"], *[d["data"] for d in p["datasets"]])),
            ("Top métiers", ["Métier", "Salariés à traiter"], zip(data["job"]["labels"], data["job"]["data"])),
            ("Coût par pôle et par action", ["Pôle"] + [d["label"] for d in c["datasets"]] + [f"Total ({UNITE})"],
             zip(c["labels"], *[d["data"] for d in c["datasets"]], c["data"])),
            ("Signaux déclencheurs", ["Signal", "Salariés"], zip(data["flags"]["labels"], data["flags"]["data"])),
        ]
    ], ensure_ascii=False).replace("<", "\\u003c")
    plotly_js = (VENDOR / "plotly.min.js").read_text(encoding="utf-8")
    xlsx_js = (VENDOR / "xlsx.full.min.js").read_text(encoding="utf-8")

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repères — Anomalies salariales</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='3' fill='%23e9a21b'/%3E%3Crect x='9' y='9' width='14' height='14' fill='%23fff'/%3E%3Crect x='15' y='4' width='2' height='24' fill='%234a2c1d'/%3E%3C/svg%3E">
<script>{plotly_js}</script>
<script>{xlsx_js}</script>
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
.page-hint {{ font-size: 13px; color: var(--muted); text-align: right; }}

.panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); min-width: 0; }}
.panel-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 16px;
  background: var(--panel-head); border-bottom: 1px solid var(--line); border-radius: var(--radius) var(--radius) 0 0; }}
.panel-title {{ font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .4px; }}
.panel-unit {{ font-size: 12px; color: var(--faint); }}
.panel-body {{ padding: 16px; }}
.note {{ font-size: 12px; color: var(--muted); margin-top: 10px; }}

.kpis {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); margin: 0 0 16px; border-left: 4px solid var(--brand); }}
.kpis div {{ padding: 16px 20px; }}
.kpis div + div {{ border-left: 1px solid var(--line-soft); }}
.kpis dt {{ font-size: 12px; color: var(--muted); }}
.kpis dd {{ margin: 2px 0 0; font-size: 24px; font-weight: 600; white-space: nowrap; }}
.kpis dd small {{ display: block; font-size: 12px; font-weight: 400; color: var(--faint); }}
.kpis .sev {{ display: inline-block; width: 8px; height: 8px; margin-right: 6px; vertical-align: 2px; }}
.kpis .critical {{ color: {STATUS['Critical']}; }}
/* Les nombres de priorité sont des boutons (ils ouvrent la liste des salariés) : même allure que les
   autres chiffres, soulignés au survol pour montrer qu'on peut cliquer. */
.kpi-btn {{ font: inherit; color: inherit; height: auto; padding: 0; border: 0; background: none; }}
.kpi-btn:hover {{ background: none; text-decoration: underline; text-underline-offset: 4px; }}
.sev-tag {{ display: inline-block; padding: 0 6px; border-radius: 2px; font-size: 12px; font-weight: 600; }}

.grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin-bottom: 16px; }}
.full {{ grid-column: 1 / -1; }}
.graphe {{ width: 100%; }}
/* Plein écran d'un graphe (bouton « Agrandir »), comme dans la page d'exploration. */
.panel-actions {{ display: flex; align-items: center; gap: 12px; }}
.agrandir {{ display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; font-size: 12px; }}
.ico {{ width: 15px; height: 15px; flex: none; }}
.panel:fullscreen {{ display: flex; flex-direction: column; width: 100vw; height: 100vh; border: 0; border-radius: 0; overflow: hidden; background: var(--panel); }}
.panel:fullscreen > .panel-body {{ flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0; padding: 12px 24px 16px; }}
.panel:fullscreen .graphe {{ flex: 1 1 0; min-height: 360px; overflow: hidden; }}
.panel::backdrop {{ background: var(--panel); }}
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
/* Pourquoi aussi sur les en-têtes (th) : avant, le titre d'une colonne de nombres restait calé à gauche
   alors que ses nombres étaient calés à droite ; titre et valeurs ne tombaient pas l'un sous l'autre. */
.num {{ text-align: right; }}
tbody tr:hover td {{ background: var(--panel-head); }}
/* Les tableaux des « Données détaillées » ont deux à cinq colonnes : à la largeur de la page, un nom et
   son nombre se retrouvaient aux deux bouts de l'écran. Ils prennent maintenant la largeur de leur contenu. */
.data-toggle table {{ width: auto; min-width: min(560px, 100%); }}
.data-toggle th:first-child {{ min-width: 220px; }}
.data-panel summary {{ list-style: none; }}
/* Tableaux comme dans Excel : une recherche au-dessus, un bouton ▾ par colonne qui ouvre le menu de tri
   et de filtre. Un bouton foncé avec un entonnoir signale une colonne filtrée. */
.tv-tools {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 0 16px 8px; }}
.tv-tools input {{ width: min(260px, 100%); }}
.tv-count {{ font-size: 12px; color: var(--muted); }}
input[type="search"] {{ font: 13px var(--font); height: 32px; padding: 0 10px; color: var(--ink); background: var(--panel);
  border: 1px solid #c4c9cf; border-radius: var(--radius); }}
th .tv-btn {{ height: 22px; min-width: 22px; padding: 0 4px; margin-left: 4px; font-size: 11px; color: var(--muted); vertical-align: middle; }}
th .tv-btn.on {{ background: var(--brand-dark); border-color: var(--brand-dark); color: #fff; }}
.tv-menu {{ position: fixed; z-index: 60; width: min(280px, calc(100vw - 16px)); display: flex; flex-direction: column; gap: 4px;
  padding: 6px; overflow: auto; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0,0,0,.18); }}
.tv-menu > button {{ text-align: left; border-color: transparent; }}
.tv-values {{ flex: 1 1 auto; min-height: 60px; max-height: 240px; overflow: auto; padding: 4px 0; border: 1px solid var(--line-soft); }}
.tv-values label {{ display: flex; align-items: center; gap: 8px; padding: 3px 8px; font-size: 13px; cursor: pointer; }}
.tv-values label:hover {{ background: var(--panel-head); }}
.tv-values label[hidden] {{ display: none; }}
.tv-actions {{ display: flex; justify-content: flex-end; gap: 8px; padding-top: 4px; }}
button:disabled {{ opacity: .5; cursor: default; }}

.overlay {{ position: fixed; inset: 0; background: rgba(31,35,40,.45); display: flex; align-items: flex-start; justify-content: center; padding: 5vh 16px; z-index: 50; }}
.overlay[hidden] {{ display: none; }}
.overlay .panel {{ width: 100%; max-width: 1100px; max-height: 88vh; display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,.2); }}
.overlay h3 {{ font-size: 15px; font-weight: 600; }}
.overlay .sub {{ font-size: 12px; color: var(--muted); }}
/* Dans la liste des salariés, la recherche reste en haut : seul le tableau défile, avec ses en-têtes. */
.overlay .panel-body {{ display: flex; flex-direction: column; min-height: 0; padding: 0; }}
.overlay .tv-tools {{ padding: 10px 16px; border-bottom: 1px solid var(--line); }}
.overlay .table-wrap {{ flex: 1 1 auto; min-height: 0; overflow: auto; padding: 0; }}
.overlay th {{ position: sticky; top: 0; }}
.head-actions {{ display: flex; gap: 8px; flex: none; }}
button {{ font: 500 13px var(--font); height: 32px; padding: 0 12px; background: var(--panel); color: var(--ink);
  border: 1px solid #c4c9cf; border-radius: var(--radius); cursor: pointer; }}
button:hover {{ background: var(--panel-head); border-color: var(--faint); }}
button:focus-visible, summary:focus-visible, input:focus-visible {{ outline: 2px solid var(--brand); outline-offset: 2px; }}

footer {{ margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--line); font-size: 12px; color: var(--faint); }}

/* Six chiffres clés : trois par ligne sur un écran moyen, deux sur un téléphone. Le premier de chaque
   ligne n'a pas de trait à gauche. */
@media (max-width: 1000px) {{
  .kpis {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  .kpis div:nth-child(3n+1) {{ border-left: 0; }}
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
  .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .kpis div:nth-child(even) {{ border-left: 1px solid var(--line-soft); }}
  .kpis div:nth-child(odd) {{ border-left: 0; }}
}}
@media print {{
  body {{ background: #fff; }}
  .panel {{ break-inside: avoid; }}
  .page-hint, .overlay, .agrandir {{ display: none; }}
}}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand"><span class="brand-mark" aria-hidden="true"></span>Repères<span class="brand-sub">Détection des anomalies salariales</span></div>
  <dl class="context">
    <div><dt>Effectif analysé</dt><dd>{fmt_int(kpis['effectif'])} salariés</dd></div>
    <div><dt>Montants</dt><dd>{UNITE} (milliers de MAD)</dd></div>
    <div><dt>Généré le</dt><dd>{generated}</dd></div>
  </dl>
</header>
<main>
  <div class="page-head">
    <div><p class="crumb">Rémunération › Anomalies</p><h1>Tableau de bord des anomalies</h1></div>
    <p class="page-hint">Cliquez une barre, un point ou un nombre de priorité pour afficher les salariés concernés.<br>
      Molette pour zoomer, double-clic pour revenir, « Agrandir » pour le plein écran.</p>
  </div>

  <dl class="panel kpis">
    <div><dt>À traiter</dt><dd>{fmt_num(round(pct, 1))} %<small>{fmt_int(kpis['a_traiter'])} salariés</small></dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Critical']}"></span>Critiques</dt><dd class="critical"><button class="kpi-btn" type="button" data-sev="Critical">{fmt_int(kpis['Critical'])}</button></dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Major']}"></span>Majeures</dt><dd><button class="kpi-btn" type="button" data-sev="Major">{fmt_int(kpis['Major'])}</button></dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Minor']}"></span>Mineures</dt><dd><button class="kpi-btn" type="button" data-sev="Minor">{fmt_int(kpis['Minor'])}</button></dd></div>
    <div><dt><span class="sev" style="background:{STATUS['Info']}"></span>{SEVERITY_FR['Info']}</dt><dd><button class="kpi-btn" type="button" data-sev="Info">{fmt_int(kpis['Info'])}</button></dd></div>
    <div><dt>Coût d'ajustement total</dt><dd>{fmt_int(kpis['cout_total'])}<small>{UNITE}</small></dd></div>
  </dl>

  <div class="grid">
    <section class="panel full">
      <div class="panel-head"><h2 class="panel-title">Anomalies à traiter par pôle</h2><span class="panel-unit">salariés</span></div>
      <div class="panel-body"><div class="graphe" id="chart-pole"></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Top 10 métiers concernés</h2><span class="panel-unit">salariés à traiter</span></div>
      <div class="panel-body"><div class="graphe" id="chart-job"></div>
        <p class="note">Salariés à traiter (priorité Critique, Majeure ou Mineure) : les 10 métiers qui en comptent le plus.</p></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Coût d'ajustement par pôle et par action</h2><span class="panel-unit">{UNITE}</span></div>
      <div class="panel-body"><div class="graphe" id="chart-cost"></div>
        <p class="note">Remise au Min : salaires sous le Min de la grille. Rapprochement du Mid : salaires trop bas
          dans la grille (CompaRatio sous {c['seuil']}).</p></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Signaux déclencheurs</h2><span class="panel-unit">salariés</span></div>
      <div class="panel-body"><div class="graphe" id="chart-flags"></div>
        <p class="note">Un salarié peut déclencher plusieurs signaux.</p></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Score général</h2><span class="panel-unit">salariés par tranche de score</span></div>
      <div class="panel-body"><div class="graphe" id="chart-risk"></div>
        <p class="note">Le score général réunit le score de règles et le score IA ; c'est lui qui fixe la priorité.</p></div>
    </section>
    <section class="panel full">
      <div class="panel-head"><h2 class="panel-title">Écarts de salaire hommes / femmes</h2><span class="panel-unit">par métier et niveau</span></div>
      <div class="panel-body">
        <div class="views" id="gap-views" role="group" aria-label="Écarts à afficher"></div>
        <div class="graphe" id="chart-gap"></div>
        <p class="note">Chaque barre compare le salaire médian (celui du milieu) des hommes à celui des femmes, à métier
          et niveau égaux : +10 % veut dire que les hommes touchent 10 % de plus. Sous chaque métier, le nombre de
          femmes et d'hommes comparés : sur quelques personnes, un seul salaire suffit à créer un gros écart. Un métier
          sans femme ou sans homme dans le niveau n'apparaît pas.</p>
      </div>
    </section>
    <details class="panel full data-panel">
      <summary class="panel-head"><h2 class="panel-title">Données détaillées</h2><span class="panel-unit">afficher</span></summary>
      <div id="detail-tables"></div>
    </details>
  </div>

  <footer>Restitution des résultats de la détection (src), sans recalcul.</footer>
</main>

<div class="overlay" id="panel-overlay" hidden>
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="panel-title">
    <div class="panel-head">
      <div><h3 id="panel-title">—</h3><div class="sub" id="panel-sub"></div></div>
      <div class="head-actions"><button id="panel-export" type="button">Exporter (Excel)</button><button id="panel-close" type="button" aria-label="Fermer">Fermer</button></div>
    </div>
    <div class="panel-body" id="panel-body"></div>
  </div>
</div>

<script>
const DATA = {data_json};
const NAMES = {names_json};
const STATUS = {json.dumps(STATUS)};
const TABLES = {tables_json};

// ---- Liste des salariés concernés (clic sur une barre, un point ou un nombre de priorité) ----
const RCOLS = DATA.records.cols, RROWS = DATA.records.rows, RIDX = {{}};
RCOLS.forEach((c, i) => RIDX[c] = i);
const MAX_ROWS_SHOWN = 300;
const NUM = new Intl.NumberFormat('fr-FR', {{ maximumFractionDigits: 2 }});
const aTraiter = r => r[RIDX.Severity] !== 'Info';

const overlay = document.getElementById('panel-overlay');
const panelTitle = document.getElementById('panel-title');
const panelSub = document.getElementById('panel-sub');
const panelBody = document.getElementById('panel-body');
let view = null, lastTitle = '';
document.getElementById('panel-close').addEventListener('click', closePanel);
overlay.addEventListener('click', e => {{ if (e.target === overlay) closePanel(); }});
// Échap ferme d'abord le menu d'une colonne s'il est ouvert, et seulement ensuite la liste.
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') {{ if (menu) closeMenu(true); else closePanel(); }} }});

function closePanel() {{ overlay.hidden = true; }}

function escapeText(value) {{
  const cell = document.createElement('span');
  cell.textContent = value === null ? '' : String(value);
  return cell.innerHTML;
}}
// Le texte affiché d'une case : priorité et signaux en français, nombres au format français. La
// recherche et les filtres travaillent sur ce texte, pour qu'on retrouve exactement ce qu'on lit.
function cellText(col, v) {{
  if (v === null || v === undefined) return '';
  if (col === 'Severity') return NAMES.sev[v] || v;
  if (col === 'Rule_Flags') return String(v).split(';').filter(Boolean).map(f => NAMES.flags[f] || f).join(', ');
  if (typeof v === 'number') return NUM.format(v);
  return String(v);
}}
function cellHtml(col, v) {{
  const text = escapeText(cellText(col, v));
  if (col === 'Severity' && STATUS[v]) return '<td><span class="sev-tag" style="background:' + STATUS[v] + '22;color:' + STATUS[v] + '">' + text + '</span></td>';
  return typeof v === 'number' ? '<td class="num">' + text + '</td>' : '<td>' + text + '</td>';
}}

function showPopulation(title, predicate) {{
  const matches = RROWS.filter(predicate);
  lastTitle = title;
  panelTitle.textContent = title;
  panelSub.textContent = NUM.format(matches.length) + ' salarié(s) concerné(s)';
  if (!matches.length) {{
    view = null;
    panelBody.innerHTML = '<p class="note" style="padding:16px">Aucun salarié ne correspond à cette sélection.</p>';
  }} else {{
    // Dessiner des milliers de lignes rendrait la page lente : au-delà de MAX_ROWS_SHOWN, les lignes
    // ne sont pas dessinées, mais elles restent comptées et exportées.
    view = tableView(panelBody, RCOLS, matches, MAX_ROWS_SHOWN);
  }}
  // Un graphe en plein écran cache tout le reste de la page : la liste s'ouvre alors par-dessus lui.
  (document.fullscreenElement || document.body).appendChild(overlay);
  overlay.hidden = false;
}}

// Export Excel des lignes gardées par la recherche et les filtres, dans l'ordre du tri, TOUTES (même
// au-delà des MAX_ROWS_SHOWN dessinées). Les nombres restent des nombres : Excel peut les additionner
// ou les trier tout de suite. Priorité et signaux gardent leur code d'origine (Critical, OUT_OF_BAND...),
// comme dans les fichiers de résultats.
document.getElementById('panel-export').addEventListener('click', () => {{
  const book = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet([RCOLS.map(c => NAMES.cols[c] || c)].concat(view ? view.rows() : [])), 'Salariés');
  XLSX.writeFile(book, 'salaries_' + lastTitle.normalize('NFD').replace(/[^\\w]+/g, '_').replace(/^_|_$/g, '').toLowerCase() + '.xlsx');
}});

// Les nombres de priorité (Critiques, Majeures, Mineures, Info) ouvrent la liste de leurs salariés.
document.querySelectorAll('.kpi-btn').forEach(b => b.addEventListener('click', () =>
  showPopulation('Priorité : ' + NAMES.sev[b.dataset.sev], r => r[RIDX.Severity] === b.dataset.sev)));

// ---- Tableaux comme dans Excel : recherche, tri et filtre par colonne ----
// Sans accents ni majuscules, pour que « ecart » trouve « Écart ». Les espaces des nombres français
// (12 345) sont des espaces spéciaux : ils deviennent des espaces ordinaires, comme ceux qu'on tape.
const norm = s => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/\\s/g, ' ').toLowerCase();
// L'ordre alphabétique français, où « 9 » vient avant « 10 » même au milieu d'un texte (« 90-100 »).
const COLLATOR = new Intl.Collator('fr', {{ numeric: true }});
const FUNNEL = '<svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><path d="M0 1h10L6 5.5V10L4 9V5.5z" fill="currentColor"/></svg>';

// Range deux lignes selon la colonne c : les nombres comme des nombres, le reste selon le texte affiché.
// Les cases vides vont toujours à la fin, dans un sens comme dans l'autre, comme dans Excel.
function order(x, y, c, dir) {{
  const vide = (x.t[c] === '') - (y.t[c] === '');
  if (vide || x.t[c] === '') return vide;
  const a = x.r[c], b = y.r[c];
  return dir * (typeof a === 'number' && typeof b === 'number' ? a - b : COLLATOR.compare(x.t[c], y.t[c]));
}}

// Un seul menu de colonne ouvert à la fois, pour toute la page.
let menu = null, menuBtn = null;
function closeMenu(refocus) {{
  if (!menu) return;
  menu.remove();
  menuBtn.setAttribute('aria-expanded', 'false');
  // Au clavier, on revient sur le bouton ▾ de la colonne, pour ne pas perdre sa place.
  if (refocus) menuBtn.focus();
  menu = menuBtn = null;
}}
// Le menu se pose sous son bouton, ou au-dessus s'il y a plus de place, sans déborder de l'écran.
function placeMenu() {{
  const r = menuBtn.getBoundingClientRect(), below = innerHeight - r.bottom - 12, above = r.top - 12;
  const down = below >= 320 || below >= above;
  menu.style.left = Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8)) + 'px';
  menu.style.top = down ? r.bottom + 4 + 'px' : '';
  menu.style.bottom = down ? '' : innerHeight - r.top + 4 + 'px';
  menu.style.maxHeight = (down ? below : above) + 'px';
}}
// Un clic à côté ferme le menu ; si la page défile ou change de taille, il reste collé à son bouton.
document.addEventListener('pointerdown', e => {{ if (menu && !menu.contains(e.target) && !menuBtn.contains(e.target)) closeMenu(false); }});
addEventListener('scroll', () => {{ if (menu) placeMenu(); }}, true);
addEventListener('resize', () => {{ if (menu) placeMenu(); }});

// Dessine dans box un tableau avec sa recherche, son compteur, son bouton « Effacer les filtres » et un
// bouton ▾ par colonne. cols : les codes des colonnes (le nom affiché vient de NAMES.cols, sinon c'est
// le code lui-même) ; rows : les lignes ; limit : le nombre maximal de lignes dessinées. Renvoie de quoi
// relire les lignes gardées, dans l'ordre affiché (pour l'export).
function tableView(box, cols, rows, limit) {{
  const labels = cols.map(c => NAMES.cols[c] || c);
  // Le texte affiché de chaque case est calculé une seule fois : la recherche le relit à chaque frappe.
  const items = rows.map(r => {{ const t = r.map((v, i) => cellText(cols[i], v)); return {{ r, t, k: t.map(norm) }}; }});
  const filters = new Map();  // numéro de colonne -> valeurs gardées (texte affiché)
  let sort = null, shown = items;
  // Une colonne de nombres a son titre calé à droite, au-dessus de ses nombres (eux aussi à droite).
  const nums = cols.map((c, i) => rows.some(r => typeof r[i] === 'number'));
  box.innerHTML = '<div class="tv-tools"><input type="search" placeholder="Rechercher dans le tableau" aria-label="Rechercher dans le tableau">'
    + '<span class="tv-count" aria-live="polite"></span><button type="button" hidden>Effacer les filtres</button></div>'
    + '<div class="table-wrap"><table><thead><tr>'
    + labels.map((l, i) => '<th' + (nums[i] ? ' class="num"' : '') + '>' + escapeText(l) + '<button type="button" class="tv-btn" aria-haspopup="dialog" aria-expanded="false"></button></th>').join('')
    + '</tr></thead><tbody></tbody></table></div>';
  const search = box.querySelector('.tv-tools input'), count = box.querySelector('.tv-count');
  const clear = box.querySelector('.tv-tools button'), tbody = box.querySelector('tbody');
  const ths = [...box.querySelectorAll('th')], btns = ths.map(th => th.querySelector('button'));

  // Une ligne est gardée si l'une de ses cases contient le texte cherché, et si elle passe le filtre de
  // chaque colonne, sauf celui de la colonne skip (voir openMenu).
  const keep = (it, q, skip) => (!q || it.k.some(s => s.includes(q)))
    && [...filters].every(([c, vals]) => c === skip || vals.has(it.t[c]));

  function render() {{
    const q = norm(search.value.trim());
    shown = items.filter(it => keep(it, q, -1));
    if (sort) shown.sort((x, y) => order(x, y, sort.c, sort.dir));
    tbody.innerHTML = shown.slice(0, limit).map(it => '<tr>' + it.r.map((v, i) => cellHtml(cols[i], v)).join('') + '</tr>').join('');
    count.textContent = NUM.format(shown.length) + (shown.length > 1 ? ' lignes' : ' ligne') + ' sur ' + NUM.format(items.length)
      + (shown.length > limit ? " — les " + limit + " premières sont affichées, l'export les contient toutes" : '');
    clear.hidden = !q && !filters.size;
    btns.forEach((b, c) => {{
      const on = filters.has(c), dir = sort && sort.c === c ? sort.dir : 0;
      // Comme l'entonnoir d'Excel : une colonne filtrée se voit sur son bouton ; une flèche montre le tri.
      b.classList.toggle('on', on);
      b.innerHTML = (on ? FUNNEL : '') + (dir > 0 ? '↑' : dir < 0 ? '↓' : '') + '▾';
      b.setAttribute('aria-label', 'Trier et filtrer : ' + labels[c] + (on ? ' (filtrée)' : ''));
      if (dir) ths[c].setAttribute('aria-sort', dir > 0 ? 'ascending' : 'descending'); else ths[c].removeAttribute('aria-sort');
    }});
  }}

  function openMenu(c, btn) {{
    closeMenu(false);
    // Comme dans Excel, le menu liste les valeurs des lignes que laissent passer la recherche et les
    // filtres des AUTRES colonnes : celui de cette colonne est justement en train d'être choisi.
    const q = norm(search.value.trim()), first = new Map();
    items.forEach(it => {{ if (!first.has(it.t[c]) && keep(it, q, c)) first.set(it.t[c], it); }});
    const vals = [...first.keys()].sort((a, b) => order(first.get(a), first.get(b), c, 1));
    const isNum = items.some(it => typeof it.r[c] === 'number'), checked = filters.get(c);
    menu = document.createElement('div');
    menu.className = 'tv-menu';
    menu.setAttribute('role', 'dialog');
    menu.setAttribute('aria-label', 'Trier et filtrer : ' + labels[c]);
    menu.innerHTML = '<button type="button">' + (isNum ? 'Trier du plus petit au plus grand' : 'Trier de A à Z') + '</button>'
      + '<button type="button">' + (isNum ? 'Trier du plus grand au plus petit' : 'Trier de Z à A') + '</button>'
      + '<input type="search" placeholder="Rechercher" aria-label="Rechercher une valeur">'
      + '<div class="tv-values"><label><input type="checkbox"> (Tout sélectionner)</label>'
      + vals.map((v, i) => '<label><input type="checkbox" data-i="' + i + '"' + (!checked || checked.has(v) ? ' checked' : '') + '> '
        + (v === '' ? '(Vides)' : escapeText(v)) + '</label>').join('')
      + '</div><div class="tv-actions"><button type="button">OK</button><button type="button">Annuler</button></div>';
    menuBtn = btn;
    btn.setAttribute('aria-expanded', 'true');
    box.appendChild(menu);
    placeMenu();

    const [asc, desc, ok, cancel] = menu.querySelectorAll('button');
    const find = menu.querySelector('input[type="search"]'), all = menu.querySelector('.tv-values input');
    const boxes = [...menu.querySelectorAll('[data-i]')];
    // Les cases visibles : celles que laisse la petite recherche du menu.
    const visible = () => boxes.filter(x => !x.parentNode.hidden);
    // « (Tout sélectionner) » est coché quand tout est coché, à moitié quand une partie l'est. Sans
    // aucune valeur cochée, le tableau serait vide : OK est alors grisé, comme dans Excel.
    const sync = () => {{
      const v = visible(), n = v.filter(x => x.checked).length;
      all.checked = n > 0 && n === v.length;
      all.indeterminate = n > 0 && n < v.length;
      ok.disabled = !n;
    }};
    menu.querySelector('.tv-values').addEventListener('change', e => {{
      if (e.target === all) visible().forEach(x => x.checked = all.checked);
      sync();
    }});
    find.addEventListener('input', () => {{
      const s = norm(find.value.trim());
      boxes.forEach(x => x.parentNode.hidden = !norm(x.parentNode.textContent).includes(s));
      sync();
    }});
    asc.addEventListener('click', () => {{ sort = {{ c, dir: 1 }}; closeMenu(true); render(); }});
    desc.addEventListener('click', () => {{ sort = {{ c, dir: -1 }}; closeMenu(true); render(); }});
    // OK garde les valeurs cochées ET visibles : chercher « fin » puis valider ne garde que les valeurs
    // qui contiennent « fin », comme dans Excel. Tout garder revient à ne plus filtrer la colonne.
    ok.addEventListener('click', () => {{
      const kept = visible().filter(x => x.checked).map(x => vals[x.dataset.i]);
      if (kept.length === vals.length) filters.delete(c); else filters.set(c, new Set(kept));
      closeMenu(true);
      render();
    }});
    cancel.addEventListener('click', () => closeMenu(true));
    sync();
    asc.focus();
  }}

  search.addEventListener('input', render);
  // « Effacer les filtres » vide aussi la recherche : le tableau revient complet (le tri, lui, reste).
  clear.addEventListener('click', () => {{ filters.clear(); search.value = ''; render(); search.focus(); }});
  btns.forEach((b, c) => b.addEventListener('click', () => {{ if (menuBtn === b) closeMenu(false); else openMenu(c, b); }}));
  render();
  return {{ rows: () => shown.map(it => it.r) }};
}}

// ---- Données détaillées : un tableau repliable par graphique ----
// Ces tableaux sont courts : toutes leurs lignes sont dessinées (pas de limite).
TABLES.forEach(t => {{
  const d = document.createElement('details');
  d.className = 'data-toggle';
  d.innerHTML = '<summary>' + escapeText(t.title) + '</summary><div></div>';
  document.getElementById('detail-tables').appendChild(d);
  tableView(d.lastChild, t.cols, t.rows, Infinity);
}});

// ---- Graphiques : Plotly, avec les mêmes réglages que la page d'exploration de visualisation/ ----
const POLICE = "'Segoe UI', system-ui, sans-serif";
const ENCRE = '#1f2328', GRIS = '#5f6670', GRILLE = '#eceef1', TRAIT = '#dde0e4';
Plotly.register({{
  moduleType: 'locale', name: 'fr',
  dictionary: {{
    'Zoom': 'Zoom', 'Pan': 'Déplacer', 'Zoom in': 'Zoom avant', 'Zoom out': 'Zoom arrière', 'Autoscale': 'Ajuster aux données',
    'Reset axes': 'Revenir à la vue de départ', 'Reset view': 'Revenir à la vue de départ',
    'Download plot as a PNG': 'Enregistrer en image (PNG)', 'Download plot': 'Enregistrer en image',
    'Double-click to zoom back out': 'Double-cliquer pour revenir à la vue de départ',
  }},
  format: {{ decimal: ',', thousands: ' ' }},
}});
// Molette pour zoomer ; au survol, une barre d'outils en haut à droite (zoom, déplacer, revenir, image).
const CONFIG = {{
  locale: 'fr', displaylogo: false, scrollZoom: true, responsive: true,
  modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d', 'toggleSpikelines', 'hoverClosestCartesian', 'hoverCompareCartesian'],
  toImageButtonOptions: {{ format: 'png', scale: 2 }},
}};
const AXE = {{ gridcolor: GRILLE, linecolor: TRAIT, zeroline: false, automargin: true, tickfont: {{ size: 12, color: GRIS }} }};
const titreAxe = texte => ({{ text: texte, font: {{ size: 12, color: GRIS }}, standoff: 12 }});

// Pour que tout s'aligne : les deux graphes d'une même rangée ont la même hauteur et les mêmes marges
// haute et basse (leurs axes tombent à la même hauteur), et tous les graphes à barres horizontales ont
// la même marge gauche, mesurée sur le plus long nom (leurs barres partent du même endroit).
// MARGE_TITRE : la marge basse d'une rangée où l'un des graphes a un titre sous son axe.
const MARGE = {{ t: 32, b: 36, r: 24 }}, MARGE_TITRE = 64;
const H_POLE = 260, H_RANGEE = 400;
const mesure = document.createElement('canvas').getContext('2d');
mesure.font = '12px ' + POLICE;
const largeur = textes => Math.ceil(Math.max(0, ...textes.map(t => mesure.measureText(String(t)).width)));
const MARGE_G = largeur([...DATA.pole.labels, ...DATA.job.labels, ...DATA.cost.labels, ...DATA.flags.labels]) + 24;

// En plein écran, le graphe prend toute la hauteur que lui laisse son panneau (voir « Agrandir », plus bas).
const hauteurDisponible = div => Math.max(360, Math.floor(div.getBoundingClientRect().height));

// Dessine le graphe id ; clic(point) ouvre la liste des salariés derrière la barre ou le point cliqué.
function dessiner(id, traces, L, hauteur, clic) {{
  const div = document.getElementById(id);
  div.dataset.hauteur = hauteur;   // la hauteur normale, reprise en sortant du plein écran
  if (document.fullscreenElement && document.fullscreenElement.contains(div)) hauteur = hauteurDisponible(div);
  Object.assign(L, {{
    height: hauteur, margin: {{ ...MARGE, l: MARGE_G, ...(L.margin || {{}}) }}, paper_bgcolor: '#fff', plot_bgcolor: '#fff',
    font: {{ family: POLICE, size: 12, color: GRIS }}, separators: ', ',
    hoverlabel: {{ bgcolor: ENCRE, bordercolor: ENCRE, font: {{ family: POLICE, size: 12, color: '#fff' }}, align: 'left' }},
    // La légende se pose au-dessus du graphe, sur son bord gauche : à la même place dans tous les panneaux.
    legend: {{ orientation: 'h', x: 0, xanchor: 'left', y: 1, yanchor: 'bottom', font: {{ size: 12, color: ENCRE }}, ...(L.legend || {{}}) }},
  }});
  Plotly.react(div, traces, L, CONFIG).then(gd => {{
    // Chaque dessin remplace le clic du précédent (le graphe des écarts hommes / femmes change de vue).
    gd.removeAllListeners('plotly_click');
    if (clic) gd.on('plotly_click', e => {{ if (e.points[0]) clic(e.points[0]); }});
  }});
}}

// Barres horizontales, la première catégorie en haut. Les barres font la même épaisseur (18 px) dans
// tous les graphes, qu'il y ait 5 pôles ou 10 métiers.
function barresH(categories, hauteur, L = {{}}) {{
  const place = (hauteur - MARGE.t - ((L.margin && L.margin.b) || MARGE.b)) / Math.max(categories.length, 1);
  return {{
    ...L, barmode: 'relative', bargap: Math.min(0.8, Math.max(0.15, 1 - 18 / place)),
    // ',d' : des nombres entiers avec une espace pour les milliers (1 000, 20 000), pas « 1000 » ni « 20k ».
    xaxis: {{ ...AXE, tickformat: ',d', ...(L.xaxis || {{}}) }},
    yaxis: {{ ...AXE, type: 'category', categoryorder: 'array', categoryarray: categories, autorange: 'reversed',
             showgrid: false, ticklabelstandoff: 8, ...(L.yaxis || {{}}) }},
  }};
}}

// Une barre par pôle, découpée par priorité ; une priorité sans aucun salarié n'est pas affichée.
const poleSets = DATA.pole.datasets.filter(d => d.data.some(v => v > 0));
dessiner('chart-pole', poleSets.map(d => ({{
  type: 'bar', orientation: 'h', name: d.label, y: DATA.pole.labels, x: d.data, marker: {{ color: d.color }},
  hovertemplate: '%{{y}} · ' + d.label + '<br><b>%{{x:,}} salariés</b><extra></extra>',
}})), barresH(DATA.pole.labels, H_POLE), H_POLE, p => {{
  const pole = DATA.pole.labels[p.pointNumber], sev = poleSets[p.curveNumber];
  showPopulation(pole + ' — ' + sev.label, r => r[RIDX.Entite_N1] === pole && r[RIDX.Severity] === sev.code);
}});

dessiner('chart-job', [{{
  type: 'bar', orientation: 'h', y: DATA.job.labels, x: DATA.job.data, marker: {{ color: '{SLATE}' }},
  hovertemplate: '%{{y}}<br><b>%{{x:,}} salariés à traiter</b><extra></extra>',
}}], barresH(DATA.job.labels, H_RANGEE), H_RANGEE, p => {{
  const label = DATA.job.labels[p.pointNumber];
  showPopulation('Métier : ' + label, r => r[RIDX.Job_Family] === label && aTraiter(r));
}});

// Une barre par pôle, découpée par action : on voit ce que coûte chaque cible d'ajustement.
const costSets = DATA.cost.datasets;
dessiner('chart-cost', costSets.map(d => ({{
  type: 'bar', orientation: 'h', name: d.label, y: DATA.cost.labels, x: d.data, customdata: d.n, marker: {{ color: d.color }},
  hovertemplate: '%{{y}} · ' + d.label + '<br><b>%{{x:,.1f}} {UNITE}</b> (%{{customdata:,}} salariés)<extra></extra>',
}})), barresH(DATA.cost.labels, H_RANGEE), H_RANGEE, p => {{
  const pole = DATA.cost.labels[p.pointNumber], action = costSets[p.curveNumber];
  showPopulation(pole + ' — ' + action.label, r => r[RIDX.Entite_N1] === pole && r[RIDX.Reco] === action.code);
}});

dessiner('chart-flags', [{{
  type: 'bar', orientation: 'h', y: DATA.flags.labels, x: DATA.flags.data, customdata: DATA.flags.codes, marker: {{ color: '{SLATE}' }},
  hovertemplate: '%{{y}} (%{{customdata}})<br><b>%{{x:,}} salariés</b><extra></extra>',
}}], barresH(DATA.flags.labels, H_RANGEE, {{ margin: {{ b: MARGE_TITRE }} }}), H_RANGEE, p => {{
  const code = DATA.flags.codes[p.pointNumber];
  showPopulation('Signal : ' + DATA.flags.labels[p.pointNumber], r => r[RIDX.Rule_Flags].split(';').includes(code));
}});

// Une courbe par score : combien de salariés tombent dans chaque tranche de 10 points.
const tranche = v => Math.min(Math.floor(v / 10), 9);
const tranches = DATA.scores.labels.map((_, i) => i < 9 ? 'de ' + i * 10 + ' à moins de ' + (i * 10 + 10) : 'de 90 à 100');
dessiner('chart-risk', DATA.scores.datasets.map((s, k) => ({{
  type: 'scatter', mode: 'lines+markers', name: s.label, x: DATA.scores.labels, y: s.data, customdata: tranches,
  // Le score général (le premier), celui qui fixe la priorité, en trait plus épais.
  line: {{ color: s.color, width: k ? 2 : 3 }}, marker: {{ color: s.color, size: k ? 8 : 10, line: {{ color: '#fff', width: 2 }} }},
  hovertemplate: s.label + ' %{{customdata}}<br><b>%{{y:,}} salariés</b><extra></extra>',
}})), {{
  xaxis: {{ ...AXE, type: 'category', showgrid: false, title: titreAxe('Score sur 100, par tranche de 10 points') }},
  yaxis: {{ ...AXE, rangemode: 'tozero', tickformat: ',d', title: titreAxe('Nombre de salariés') }},
  margin: {{ l: 72, b: MARGE_TITRE }},
}}, H_RANGEE, p => {{
  const s = DATA.scores.datasets[p.curveNumber];
  showPopulation(s.label + ' ' + DATA.scores.labels[p.pointNumber], r => tranche(r[RIDX[s.code]]) === p.pointNumber);
}});

// ---- Écarts hommes / femmes : les 10 plus marqués, puis un bouton par niveau ----
const GAP = DATA.gap;
const plural = (n, mot) => n + ' ' + mot + (n > 1 ? 's' : '');
const pctText = v => (v > 0 ? '+' : '') + NUM.format(v) + ' %';
const gapName = (r, avecNiveau) => r.Job_Family + (avecNiveau ? ' · niveau ' + r.Niveau : '');
// La même échelle pour toutes les vues : deux barres de même longueur montrent le même écart, d'un
// niveau à l'autre. La marge de 20 % laisse la place d'écrire l'écart au bout de la plus longue barre ;
// arrondir à 20 près garde des graduations régulières (-40 %, -20 %, 0 %...).
const gapMax = Math.ceil(Math.max(...GAP.map(r => Math.abs(r.Ecart_pct))) * 1.2 / 20) * 20;
const graduations = [];
for (let v = -gapMax; v <= gapMax; v += 20) graduations.push(v);
const gapViews = [{{ name: 'Les 10 plus marqués', rows: [...GAP].sort((a, b) => Math.abs(b.Ecart_pct) - Math.abs(a.Ecart_pct)).slice(0, 10) }}]
  .concat([...new Set(GAP.map(r => r.Niveau))].sort((a, b) => a - b).map(g => ({{
    // Dans un niveau, du plus favorable aux hommes (en haut) au plus favorable aux femmes (en bas).
    name: 'Niveau ' + g, niveau: g, rows: GAP.filter(r => r.Niveau === g).sort((a, b) => b.Ecart_pct - a.Ecart_pct),
  }})));
let gapRows = [];
// Deux lignes devant chaque barre : le métier (et le niveau s'ils sont mélangés), puis les effectifs.
const effectifs = r => plural(r.F, 'femme') + ' · ' + plural(r.M, 'homme');
const gapSurvol = r => '<b>' + escapeText(gapName(r, true)) + '</b>'
  + '<br>Médiane femmes : ' + NUM.format(r.Median_F) + ' {UNITE} (' + plural(r.F, 'femme') + ')'
  + '<br>Médiane hommes : ' + NUM.format(r.Median_M) + ' {UNITE} (' + plural(r.M, 'homme') + ')'
  + '<br>Les hommes touchent ' + NUM.format(Math.abs(r.Ecart_pct)) + ' % de ' + (r.Ecart_pct < 0 ? 'moins' : 'plus') + ' que les femmes';
// La marge gauche se règle sur le plus long nom de toutes les vues : le zéro ne bouge pas quand on change de vue.
const MARGE_GAP = largeur(GAP.flatMap(r => [gapName(r, true), effectifs(r)])) + 24;

function showGapView(view, button) {{
  gapRows = view.rows;
  const noms = gapRows.map(r => escapeText(gapName(r, !view.niveau)) + '<br>' + effectifs(r));
  // Deux séries : or = femmes mieux payées (écart négatif), ardoise = hommes mieux payés. La légende le dit.
  const serie = (garder, nom, couleur) => {{
    const idx = gapRows.map((r, i) => i).filter(i => garder(gapRows[i].Ecart_pct));
    return {{ type: 'bar', orientation: 'h', name: nom, y: idx.map(i => noms[i]), x: idx.map(i => gapRows[i].Ecart_pct), customdata: idx,
      marker: {{ color: couleur }}, text: idx.map(i => pctText(gapRows[i].Ecart_pct)), textposition: 'outside', cliponaxis: false,
      textfont: {{ size: 12, color: ENCRE }}, hovertext: idx.map(i => gapSurvol(gapRows[i])), hovertemplate: '%{{hovertext}}<extra></extra>' }};
  }};
  // 46 px par métier : les barres gardent leur épaisseur, quel que soit le nombre de métiers du niveau.
  const h = Math.max(360, MARGE.t + MARGE_TITRE + 46 * gapRows.length);
  dessiner('chart-gap', [serie(v => v <= 0, 'Femmes mieux payées', '{GOLD}'), serie(v => v > 0, 'Hommes mieux payés', '{SLATE}')],
    barresH(noms, h, {{
      xaxis: {{ range: [-gapMax, gapMax], tickvals: graduations, ticktext: graduations.map(v => (v > 0 ? '+' : '') + v + ' %'),
               zeroline: true, zerolinecolor: '#8b929b', zerolinewidth: 1,
               title: titreAxe('Salaire médian des hommes comparé à celui des femmes (en %)') }},
      // La légende au-dessus du zéro : or à gauche, ardoise à droite, comme les barres.
      legend: {{ x: 0.5, xanchor: 'center' }},
      margin: {{ l: MARGE_GAP, b: MARGE_TITRE }},
    }}), h, p => {{
      const r = gapRows[p.customdata];
      showPopulation(gapName(r, true), x => x[RIDX.Job_Family] === r.Job_Family && x[RIDX.Niveau] === r.Niveau);
    }});
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

// ---- Agrandir un graphe en plein écran : le même bouton que dans la page d'exploration ----
// En plein écran, le graphe prend toute la hauteur disponible ; « Réduire » ou la touche Échap ramène à la page.
const AGRANDIR = '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/></svg>Agrandir';
const REDUIRE = '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M6 2v4H2M14 6h-4V2M10 14v-4h4M2 10h4v4"/></svg>Réduire';
const boutonsPlein = [];
if (document.fullscreenEnabled) document.querySelectorAll('section.panel').forEach(section => {{
  if (!section.querySelector('.graphe')) return;
  // Le bouton se range à droite de l'en-tête, après l'unité.
  const tete = section.querySelector('.panel-head'), actions = document.createElement('div');
  actions.className = 'panel-actions';
  const unite = tete.querySelector('.panel-unit');
  if (unite) actions.append(unite);
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'agrandir';
  b.onclick = () => document.fullscreenElement === section ? document.exitFullscreen() : section.requestFullscreen();
  actions.append(b);
  tete.append(actions);
  boutonsPlein.push([b, section]);
}});
function pleinEcran() {{
  for (const [b, section] of boutonsPlein) {{
    const plein = document.fullscreenElement === section;
    b.innerHTML = plein ? REDUIRE : AGRANDIR;
    b.title = plein ? 'Revenir à la page (Échap)' : 'Afficher ce graphe en plein écran';
  }}
  // En sortant du plein écran, la liste des salariés (ouverte par-dessus le graphe) revient dans la page.
  if (!document.fullscreenElement && overlay.parentNode !== document.body) document.body.appendChild(overlay);
  // Le graphe prend la largeur et la hauteur que lui laisse le plein écran, puis reprend les siennes au
  // retour (largeur « null » : il suit de nouveau la largeur de la page).
  requestAnimationFrame(() => document.querySelectorAll('.graphe.js-plotly-plot').forEach(div => {{
    const plein = document.fullscreenElement && document.fullscreenElement.contains(div);
    if (plein) Plotly.relayout(div, {{ height: hauteurDisponible(div), width: Math.floor(div.getBoundingClientRect().width) }});
    else if (div.layout.width || div.layout.height !== Number(div.dataset.hauteur)) Plotly.relayout(div, {{ height: Number(div.dataset.hauteur), width: null }});
  }}));
}}
document.addEventListener('fullscreenchange', pleinEcran);
pleinEcran();
</script>
</body>
</html>
"""


def generate_dashboard(df: pd.DataFrame, gg: pd.DataFrame, rule_params: dict, dossier) -> Path:
    """Crée le tableau de bord à partir des deux tableaux et des réglages, et l'enregistre dans dossier.

    Le nom du fichier porte la date et l'heure (dashboard_anomalies_2026-10-02_14-35-08.html) : un
    nouveau lancement ne remplace pas le tableau de bord précédent, et les noms se rangent d'eux-mêmes
    du plus ancien au plus récent.
    """
    maintenant = datetime.now()
    out_html = Path(dossier) / f"dashboard_anomalies_{maintenant:%Y-%m-%d_%H-%M-%S}.html"
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(build_html(build_data(df, gg, rule_params), maintenant), encoding="utf-8")
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
    df = preparer_employes(projet / "input" / "employes.xlsx",
                           projet / "input" / "bands.xlsx",
                           projet / "input" / "market.xlsx")
    gg = gender_gap_analysis(df)
    df = former_cohortes(df, rule_params)
    df = apply_rulebook(df, rule_params)
    df = ml_anomaly(df, rule_params)
    df = apply_ml_strong_signal(df, rule_params)
    df = aggregate_risk(df, rule_params)
    df = recommendations(df, rule_params)

    sortie = generate_dashboard(df, gg, rule_params, projet / "output" / "dashboard")
    print(f"Tableau de bord enregistré dans : {sortie}")
