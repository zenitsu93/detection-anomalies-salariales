#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TABLEAU DE BORD HTML DES ANOMALIES
==================================

Ce fichier crée un tableau de bord HTML (graphiques Chart.js) à partir de :
- df : le DataFrame des salariés rendu par anomaly_recommandations.py, avec le score général
  (RiskScore) et la priorité (Severity) ajoutés par anomaly_score_general.py ;
- gg : le tableau rendu par anomaly_ecarts_hommes_femmes.py ;
- rule_params : les réglages de config/rules.yaml, pour afficher les seuils de la règle CompaRatio.
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

CHARTJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.1/chart.umd.min.js"
# SheetJS écrit le fichier Excel de la liste des salariés directement dans le navigateur.
XLSX_URL = "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"

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

# Position dans la grille : ardoise pour les tranches hors de la zone normale du CompaRatio (celles qui
# comptent), gris clair pour celles qui sont dedans.
ZONE_IN = "#cfd5dc"

# Les étiquettes traduites pour l'écran ; le code d'origine reste visible dans l'infobulle.
FLAG_FR = {
    "OUT_OF_BAND": "Hors grille",
    "COMPA_RATIO": "Position dans la grille",
    "MARKET_GAP": "Écart au marché",
    "PEER_OUTLIER": "Écart aux collègues",
    "MIN_SALARY": "Sous le salaire minimum",
    "ML_STRONG_SIGNAL": "Signal statistique fort",
}
# Les colonnes de la liste des salariés (clic sur une barre), et leur nom affiché.
COL_FR = {
    "Matricule": "Matricule", "Entite_N1": "Pôle", "Job_Family": "Métier", "Job_Title": "Poste",
    "Grade": "Grade", "Sexe": "Sexe", "Severity": "Priorité", "RiskScore": "Score général",
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

    # Position dans la grille : les CompaRatio (arrondis comme dans la liste, pour que les comptes
    # collent) par tranches de 0,05, de « moins de 0,60 » (tranche 0) à « 1,40 et plus » (tranche 17).
    # Une tranche est dans la zone si elle tient entre les deux seuils de la règle CompaRatio. Les
    # salariés sans grille n'ont pas de CompaRatio : ils ne sont pas comptés.
    lo, hi = rule_params["compa_ratio_low"], rule_params["compa_ratio_high"]
    compa = df["CompaRatio"].round(2).dropna()
    tranche_cr = (np.floor(((compa - 0.60) / 0.05).round(6)) + 1).clip(0, 17).astype(int)
    debuts = [round(0.60 + 0.05 * k, 2) for k in range(16)]
    # Le nombre hors zone se compte sur les valeurs exactes, comme la règle CompaRatio : il est égal au
    # nombre de salariés qui ont le signal « Position dans la grille ».
    hors_zone = int(((df["CompaRatio"] < lo) | (df["CompaRatio"] > hi)).sum())

    # Carte métier × grade : pour chaque case, l'effectif et le nombre de salariés de chaque priorité.
    carte = pd.crosstab([df["Job_Family"], df["Grade"]], df["Severity"]).reindex(columns=SEVERITY_ORDER, fill_value=0)
    metiers, grades = sorted(df["Job_Family"].unique()), sorted(df["Grade"].unique())
    cases = [[{"n": int(carte.loc[(m, g)].sum()), "C": int(carte.loc[(m, g), "Critical"]),
               "M": int(carte.loc[(m, g), "Major"]), "m": int(carte.loc[(m, g), "Minor"])}
              if (m, g) in carte.index else None for g in grades] for m in metiers]
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
                              for code, (nom, couleur) in ACTIONS.items()]},
        "compa": {
            "labels": [f"< {virgule(0.60)}"] + [virgule(d) for d in debuts] + [f"≥ {virgule(1.40)}"],
            "ranges": [f"moins de {virgule(0.60)}"] + [f"de {virgule(d)} à moins de {virgule(d + 0.05)}" for d in debuts]
                      + [f"{virgule(1.40)} et plus"],
            "data": tranche_cr.value_counts().reindex(range(18), fill_value=0).tolist(),
            "inside": [False] + [lo - 1e-9 <= d and d + 0.05 <= hi + 1e-9 for d in debuts] + [False],
            "lo": virgule(lo), "hi": virgule(hi), "hors": hors_zone, "total": len(compa),
        },
        "carte": {"metiers": metiers, "grades": [int(g) for g in grades], "cases": cases},
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

    p, c, cr = data["pole"], data["cost"], data["compa"]
    pct_hors = cr["hors"] / cr["total"] * 100 if cr["total"] else 0.0
    # Les tableaux des « Données détaillées » partent en JSON (titre, colonnes, lignes) et non plus en
    # HTML tout fait : la page les dessine elle-même, avec la même recherche et les mêmes filtres que la
    # liste des salariés. Pas de tableau des écarts hommes / femmes (le graphique par grade le remplace)
    # ni du score général (ses trois courbes et leur infobulle donnent déjà les nombres).
    tables_json = json.dumps([
        {"title": titre, "cols": entetes, "rows": list(lignes)}
        for titre, entetes, lignes in [
            ("Anomalies à traiter par pôle", ["Pôle"] + [d["label"] for d in p["datasets"]],
             zip(p["labels"], *[d["data"] for d in p["datasets"]])),
            ("Top métiers", ["Métier", "Salariés à traiter"], zip(data["job"]["labels"], data["job"]["data"])),
            ("Coût par pôle et par action", ["Pôle"] + [d["label"] for d in c["datasets"]] + [f"Total ({UNITE})"],
             zip(c["labels"], *[d["data"] for d in c["datasets"]], c["data"])),
            ("Position dans la grille (CompaRatio)", ["Tranche", "Salariés", "Zone"],
             zip(cr["ranges"], cr["data"], ["dans la zone" if z else "hors zone" for z in cr["inside"]])),
            ("Signaux déclencheurs", ["Signal", "Salariés"], zip(data["flags"]["labels"], data["flags"]["data"])),
        ]
    ], ensure_ascii=False).replace("<", "\\u003c")

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repères — Anomalies salariales</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='3' fill='%23e9a21b'/%3E%3Crect x='9' y='9' width='14' height='14' fill='%23fff'/%3E%3Crect x='15' y='4' width='2' height='24' fill='%234a2c1d'/%3E%3C/svg%3E">
<script src="{CHARTJS_URL}"></script>
<script src="{XLSX_URL}"></script>
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
.chart-box {{ position: relative; width: 100%; }}
.h-sm {{ height: 240px; }}
.h-md {{ height: 300px; }}
.h-lg {{ height: 360px; }}
.h-xl {{ height: 520px; }}
/* Boutons de choix des écarts hommes / femmes : celui qui est affiché est foncé. */
.views {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
.views button[aria-pressed="true"] {{ background: var(--brand-dark); border-color: var(--brand-dark); color: #fff; }}
/* Petite légende écrite au-dessus d'un graphique : un carré de couleur devant chaque libellé. */
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 16px; margin-bottom: 8px; font-size: 12px; color: var(--muted); }}
.legend i {{ display: inline-block; width: 10px; height: 10px; margin-right: 6px; vertical-align: -1px; }}
/* Carte métier × grade : une case par métier et grade, plus foncée quand la part est forte. */
.heat {{ overflow-x: auto; }}
.heat th, .heat td {{ padding: 5px 6px; text-align: center; border: 0; }}
.heat th:first-child, .heat td:first-child {{ text-align: left; padding-left: 0; }}
.heat td.cell {{ cursor: pointer; font-weight: 600; font-size: 12px; border: 2px solid var(--panel); }}
.heat td.cell:hover, .heat td.cell:focus-visible {{ outline: 2px solid var(--brand-dark); outline-offset: -2px; }}
.heat td.empty {{ color: var(--faint); }}
.heat-legend {{ display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 12px; color: var(--muted); }}
.heat-legend .bar {{ width: 140px; height: 10px; background: linear-gradient(90deg, rgb(238,241,244), rgb(47,61,76)); }}

details.data-toggle {{ border-top: 1px solid var(--line-soft); }}
details.data-toggle summary {{ cursor: pointer; padding: 10px 16px; font-size: 13px; }}
details.data-toggle[open] summary {{ font-weight: 600; }}
.table-wrap {{ overflow-x: auto; padding: 0 16px 12px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; font-size: 12px; font-weight: 600; color: var(--muted); padding: 8px 12px; border-bottom: 1px solid var(--line); background: var(--panel); white-space: nowrap; }}
td {{ padding: 8px 12px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }}
.num {{ text-align: right; }}
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
  .page-hint, .overlay {{ display: none; }}
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
    <p class="page-hint">Cliquez une barre, un point ou un nombre de priorité pour afficher les salariés concernés.</p>
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
      <div class="panel-body"><div class="chart-box h-sm"><canvas id="chart-pole"></canvas></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Top 10 métiers concernés</h2><span class="panel-unit">salariés à traiter</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-job"></canvas></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Coût d'ajustement par pôle et par action</h2><span class="panel-unit">{UNITE}</span></div>
      <div class="panel-body"><div class="chart-box h-lg"><canvas id="chart-cost"></canvas></div>
        <p class="note">Remise au Min : salaires sous le Min de la grille. Rapprochement du Mid : salaires trop bas
          dans la grille (CompaRatio sous {cr['lo']}).</p></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Position dans la grille</h2><span class="panel-unit">salariés par tranche de CompaRatio</span></div>
      <div class="panel-body">
        <div class="legend"><span><i style="background:{SLATE}"></i>Hors de la zone {cr['lo']} – {cr['hi']}</span><span><i style="background:{ZONE_IN}"></i>Dans la zone</span></div>
        <div class="chart-box h-xl"><canvas id="chart-compa"></canvas></div>
        <p class="note">{fmt_num(round(pct_hors, 1))} % des salariés sont hors de la zone ({fmt_int(cr['hors'])} sur
          {fmt_int(cr['total'])}). CompaRatio = salaire ÷ milieu de la grille : 1 veut dire pile au milieu. Les
          salariés sans grille ne sont pas comptés.</p></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Carte métier × grade</h2><span class="panel-unit">part des salariés de la case</span></div>
      <div class="panel-body">
        <div class="views" id="heat-views" role="group" aria-label="Priorités à afficher"></div>
        <div class="heat" id="heat"></div>
        <div class="heat-legend"><span>0 %</span><span class="bar"></span><span id="heat-max"></span></div>
        <p class="note">Plus la case est foncée, plus la part de salariés concernés est forte. Survolez une case pour
          voir l'effectif ; cliquez pour afficher les salariés.</p></div>
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
  box.innerHTML = '<div class="tv-tools"><input type="search" placeholder="Rechercher dans le tableau" aria-label="Rechercher dans le tableau">'
    + '<span class="tv-count" aria-live="polite"></span><button type="button" hidden>Effacer les filtres</button></div>'
    + '<div class="table-wrap"><table><thead><tr>'
    + labels.map(l => '<th>' + escapeText(l) + '<button type="button" class="tv-btn" aria-haspopup="dialog" aria-expanded="false"></button></th>').join('')
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
// Réglages des barres horizontales (tous les graphiques sauf le score général et la position dans la grille).
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

// Une barre par pôle, découpée par action : on voit ce que coûte chaque cible d'ajustement.
const costSets = DATA.cost.datasets;
new Chart(document.getElementById('chart-cost'), {{
  type: 'bar',
  data: {{ labels: DATA.cost.labels, datasets: costSets.map(d => hbar(d.color, {{ label: d.label, data: d.data }})) }},
  options: hOptions({{
    plugins: {{ legend: {{ display: true, position: 'top', align: 'start', labels: {{ boxWidth: 10, boxHeight: 10, padding: 16 }} }},
               tooltip: {{ displayColors: true, callbacks: {{
                 label: c => c.dataset.label + ' : ' + NUM.format(c.parsed.x) + ' {UNITE} (' + NUM.format(costSets[c.datasetIndex].n[c.dataIndex]) + ' salariés)',
               }} }} }},
    scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }},
    onClick: (evt, els) => pick(els, (i, d) => {{
      const pole = DATA.cost.labels[i], action = costSets[d];
      showPopulation(pole + ' — ' + action.label, r => r[RIDX.Entite_N1] === pole && r[RIDX.Reco] === action.code);
    }}),
  }}),
}});

// ---- Position dans la grille : combien de salariés par tranche de CompaRatio ----
const CR = DATA.compa;
// La tranche d'un CompaRatio, calculée comme en Python (tranches de 0,05, de 0 à 17).
const trancheCR = v => Math.min(Math.max(Math.floor(+((v - 0.6) / 0.05).toFixed(6)) + 1, 0), 17);
new Chart(document.getElementById('chart-compa'), {{
  type: 'bar',
  data: {{ labels: CR.labels, datasets: [{{ data: CR.data, borderRadius: 2, maxBarThickness: 28,
    backgroundColor: CR.inside.map(dedans => dedans ? '{ZONE_IN}' : '{SLATE}') }}] }},
  options: baseOptions({{
    plugins: {{ tooltip: {{ callbacks: {{
      title: items => 'CompaRatio ' + CR.ranges[items[0].dataIndex],
      label: c => NUM.format(c.parsed.y) + ' salariés' + (CR.inside[c.dataIndex] ? ' (dans la zone)' : ' (hors zone)'),
    }} }} }},
    scales: {{
      // Étiquettes droites : quand elles manquent de place, Chart.js n'en écrit qu'une sur deux.
      x: {{ grid: {{ display: false }}, ticks: {{ maxRotation: 0, autoSkipPadding: 8 }},
            title: {{ display: true, text: 'CompaRatio (salaire ÷ milieu de la grille)' }} }},
      y: {{ beginAtZero: true, title: {{ display: true, text: 'Nombre de salariés' }} }},
    }},
    onClick: (evt, els) => pick(els, i => showPopulation('CompaRatio ' + CR.ranges[i],
      r => r[RIDX.CompaRatio] !== null && trancheCR(r[RIDX.CompaRatio]) === i)),
  }}),
}});

// ---- Carte métier × grade : la part des salariés concernés dans chaque case ----
const CARTE = DATA.carte, heat = document.getElementById('heat');
const MODES = [
  {{ name: 'Toutes priorités à traiter', count: c => c.C + c.M + c.m, test: r => aTraiter(r) }},
  {{ name: 'Critiques et majeures', count: c => c.C + c.M, test: r => ['Critical', 'Major'].includes(r[RIDX.Severity]) }},
];
// Teinte d'une case, du gris très clair (0) à l'ardoise foncée (la case la plus touchée de la carte).
const CLAIR = [238, 241, 244], FONCE = [47, 61, 76];
const teinte = t => 'rgb(' + CLAIR.map((v, k) => Math.round(v + (FONCE[k] - v) * t)).join(',') + ')';
let carteMode = MODES[0];
function showCarte(mode, button) {{
  carteMode = mode;
  // L'échelle va de 0 à la part la plus forte de la carte : sinon, avec peu de critiques, tout serait pâle.
  const parts = CARTE.cases.flat().filter(Boolean).map(c => mode.count(c) / c.n);
  const max = Math.max(...parts) || 1;
  const tete = '<tr><th>Métier</th>' + CARTE.grades.map(g => '<th>Grade ' + g + '</th>').join('') + '</tr>';
  const lignes = CARTE.metiers.map((m, i) => '<tr><td>' + escapeText(m) + '</td>' + CARTE.cases[i].map((c, j) => {{
    if (!c) return '<td class="empty">—</td>';
    const k = mode.count(c), t = k / c.n / max;
    const bulle = m + ' · grade ' + CARTE.grades[j] + ' : ' + NUM.format(k) + ' sur ' + NUM.format(c.n) + ' salariés';
    return '<td class="cell" tabindex="0" role="button" data-i="' + i + '" data-j="' + j + '" title="' + escapeText(bulle)
      + '" style="background:' + teinte(t) + ';color:' + (t > 0.55 ? '#fff' : 'var(--ink)') + '">'
      + NUM.format(Math.round(k / c.n * 100)) + ' %</td>';
  }}).join('') + '</tr>').join('');
  heat.innerHTML = '<table><thead>' + tete + '</thead><tbody>' + lignes + '</tbody></table>';
  document.getElementById('heat-max').textContent = NUM.format(Math.round(max * 100)) + ' %';
  carteButtons.forEach(b => b.setAttribute('aria-pressed', b === button));
}}
// Clic (ou Entrée au clavier) sur une case : la liste de ses salariés concernés.
function openCase(td) {{
  const m = CARTE.metiers[td.dataset.i], g = CARTE.grades[td.dataset.j];
  showPopulation(m + ' · grade ' + g + ' — ' + carteMode.name,
    r => r[RIDX.Job_Family] === m && r[RIDX.Grade] === g && carteMode.test(r));
}}
heat.addEventListener('click', e => {{ const td = e.target.closest('td.cell'); if (td) openCase(td); }});
heat.addEventListener('keydown', e => {{ const td = e.target.closest('td.cell'); if (td && e.key === 'Enter') openCase(td); }});
const carteButtons = MODES.map(mode => {{
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = mode.name;
  b.addEventListener('click', () => showCarte(mode, b));
  document.getElementById('heat-views').appendChild(b);
  return b;
}});
showCarte(MODES[0], carteButtons[0]);

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
        return ['Médiane femmes : ' + NUM.format(r.Median_F) + ' {UNITE} (' + plural(r.F, 'femme') + ')',
                'Médiane hommes : ' + NUM.format(r.Median_M) + ' {UNITE} (' + plural(r.M, 'homme') + ')',
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
