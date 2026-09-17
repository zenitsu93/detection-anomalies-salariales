#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Lecture des fichiers d'entree, mise en forme des nombres et export des resultats (CSV et Excel).

Rien dans ce fichier ne participe au calcul des anomalies : c'est uniquement la partie
"entree / sortie" du script. On y trouve : la lecture d'un CSV en devinant son separateur, le
retrait des colonnes dupliquees (ex: deux colonnes "Matricule"), la mise en forme des salaires
avec un separateur de milliers pour l'export CSV, et la generation du classeur Excel avec ses
onglets, ses couleurs et son graphique de repartition par severite.

Le calcul des anomalies lui-meme (ratios, regles, cohortes, IA, recommandations) se trouve dans
anomaly_core.py. Ce fichier est importe par detect_salary_anomalies_custom_fixed.py, qui reste le
point d'entree en ligne de commande.

Ce decoupage en plusieurs fichiers est une reorganisation du code pour le rendre plus facile a
relire et a maintenir : il ne change rien au comportement du script (memes calculs, memes
resultats).
"""

from pathlib import Path

import pandas as pd

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.formatting.rule import ColorScaleRule
    from openpyxl.chart import PieChart, Reference
except ImportError as e:
    raise SystemExit("openpyxl est requis pour l'export Excel. Installez-le via: pip install openpyxl") from e


def remove_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Supprime les colonnes dupliquées en ne conservant que la première occurrence.

    Lorsque pandas lit un CSV avec des en-têtes dupliqués, il crée des noms identiques. Cette fonction
    supprime les duplicats afin d'éviter d'avoir deux colonnes « Matricule » ou similaires.
    """
    if df.columns.duplicated().any():
        return df.loc[:, ~df.columns.duplicated()]
    return df



def read_csv_guess_sep(path: str) -> pd.DataFrame:
    """Tente de lire un fichier CSV en détectant automatiquement le séparateur.

    On tente successivement la virgule puis le point-virgule. Si le résultat
    comporte plus d'une colonne, on le retourne. À défaut, pandas détecte
    automatiquement le séparateur.

    Args:
        path: chemin vers le fichier CSV.

    Returns:
        DataFrame lu depuis le CSV.
    """
    for sep in [",", ";"]:
        try:
            df = pd.read_csv(path, sep=sep, encoding="cp1252", engine="python")
            # S'il y a plus d'une colonne, on considère que le séparateur est correct
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    # Dernier recours : détecter automatiquement
    return pd.read_csv(path, sep=None, encoding="cp1252", engine="python")



def format_numeric_fields(out: pd.DataFrame) -> pd.DataFrame:
    """Formate les colonnes numériques selon la locale utilisateur (Windows)."""
    import locale
    try:
        locale.setlocale(locale.LC_ALL, '')
    except Exception:
        locale.setlocale(locale.LC_ALL, locale.getdefaultlocale()[0])
    def fmt(x):
        if pd.isna(x):
            return ""
        try:
            return locale.format_string('%.2f', float(x), grouping=True)
        except Exception:
            return str(x)
    num_cols = ["Fixe_Annuel_MAD", "Min", "Mid", "Max", "Market_Median", "Cout_Ajustement"]
    for col in num_cols:
        if col in out.columns:
            out[col] = out[col].apply(fmt)
    return out



def to_excel_colored(df: pd.DataFrame, path_xlsx: str) -> None:
    """Exporte le DataFrame complet dans un fichier Excel avec onglets, filtres et coloration du RiskScore.

    Des feuilles séparées sont créées pour chaque niveau de sévérité, ainsi qu'un onglet de synthèse budgétaire.
    """
    import openpyxl
    from openpyxl.chart import PieChart, Reference
    path_xlsx = Path(path_xlsx)
    with pd.ExcelWriter(path_xlsx, engine="openpyxl") as xw:
        df_sorted = df.sort_values(["Severity", "RiskScore"], ascending=[True, False])
        df_sorted.to_excel(xw, sheet_name="All", index=False)
        for sev in ["Critical", "Major", "Minor", "Info"]:
            sub = df[df["Severity"] == sev].sort_values("RiskScore", ascending=False)
            if sub.empty:
                sub = df.head(0).copy()
            sub.to_excel(xw, sheet_name=sev, index=False)
        # Synthèse budgétaire (Cout_Ajustement par Entite_N1 et Severity)

        if "Cout_Ajustement" in df.columns:
            grp_cols = [c for c in ["Severity", "Entite_N1"] if c in df.columns]
            import locale
            try:
                locale.setlocale(locale.LC_ALL, '')
            except Exception:
                locale.setlocale(locale.LC_ALL, locale.getdefaultlocale()[0])
            df["Cout_Ajustement_num"] = pd.to_numeric(df["Cout_Ajustement"].str.replace(" ", ""), errors="coerce")
            synth = (df.groupby(grp_cols, dropna=False)["Cout_Ajustement_num"]
                     .sum()
                     .reset_index()
                     .sort_values(["Severity", "Cout_Ajustement_num"], ascending=[True, False]))
            # Add total row
            total = synth["Cout_Ajustement_num"].sum()
            if len(grp_cols) == 2:
                synth.loc[len(synth)] = ["TOTAL", "", total]
            else:
                synth.loc[len(synth)] = ["TOTAL", total]
            # Format numbers with locale
            if "Cout_Ajustement_num" in synth.columns:
                synth["Cout_Ajustement_num"] = synth["Cout_Ajustement_num"].apply(lambda x: locale.format_string('%.2f', x, grouping=True) if pd.notna(x) else "")
                synth = synth.rename(columns={"Cout_Ajustement_num": "Cout_Ajustement"})
            synth.to_excel(xw, sheet_name="Budget_Synthese", index=False)

        # Statistiques globales
        stats = {
            "Total anomalies": len(df),
            "Critical": (df["Severity"] == "Critical").sum(),
            "Major": (df["Severity"] == "Major").sum(),
            "Minor": (df["Severity"] == "Minor").sum(),
            "Info": (df["Severity"] == "Info").sum(),
            "Total adjustment cost": df["Cout_Ajustement"].apply(pd.to_numeric, errors="coerce").sum()
        }
        stats_df = pd.DataFrame(list(stats.items()), columns=["Metric", "Value"])
        stats_df.to_excel(xw, sheet_name="Statistics", index=False)

    wb = openpyxl.load_workbook(path_xlsx)
    # Formatting and charts
    for ws_name in ["All", "Critical", "Major", "Minor", "Info"]:
        if ws_name not in wb.sheetnames:
            continue
        ws = wb[ws_name]
        ws.freeze_panes = "A2"
        max_col = ws.max_column
        max_row = ws.max_row
        ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(max_col)}{max_row}"
        # Entêtes en gras et couleur de fond
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="FFF2F2F2", end_color="FFF2F2F2", fill_type="solid")
            cell.alignment = Alignment(vertical="center")
        header = [c.value for c in ws[1]]
        # Coloration conditionnelle sur RiskScore
        if "RiskScore" in header:
            col_idx = header.index("RiskScore") + 1
            rng = openpyxl.utils.get_column_letter(col_idx) + "2:" + openpyxl.utils.get_column_letter(col_idx) + str(max_row)
            rule = ColorScaleRule(start_type="num", start_value=0, start_color="63BE7B",
                                  mid_type="num", mid_value=50, mid_color="FFEB84",
                                  end_type="num", end_value=100, end_color="F8696B")
            ws.conditional_formatting.add(rng, rule)
        # Ajuster la largeur des colonnes
        for i, name in enumerate(header, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(40, max(12, len(str(name)) + 2))

    # Add only severity breakdown pie chart to Statistics sheet
    if "Statistics" in wb.sheetnames:
        ws = wb["Statistics"]
        pie = PieChart()
        pie.title = "Severity Breakdown"
        pie_data = Reference(ws, min_col=2, min_row=2, max_row=5)
        pie_labels = Reference(ws, min_col=1, min_row=2, max_row=5)
        pie.add_data(pie_data, titles_from_data=False)
        pie.set_categories(pie_labels)
        ws.add_chart(pie, "D2")
    wb.save(path_xlsx)



