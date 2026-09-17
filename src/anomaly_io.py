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
    supprime les duplicats afin d'éviter d'avoir deux colonnes « Matricule » ou similaires.
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
    # Dernier recours : détecter automatiquement
    return pd.read_csv(path, sep=None, encoding="cp1252", engine="python")


def format_numeric_fields(out: pd.DataFrame) -> pd.DataFrame:
    """Formate les colonnes numériques selon la locale utilisateur (Windows), pour l'export CSV
    uniquement (l'export Excel travaille directement sur les valeurs numériques, cf to_excel_colored)."""
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

    Contrairement à l'export CSV, cette fonction reçoit un DataFrame avec des colonnes numériques
    (pas de texte formaté selon la locale) : la mise en forme "milliers" est faite au niveau Excel
    via le number_format des cellules, ce qui évite tout aller-retour texte -> nombre fragile.
    """
    path_xlsx = Path(path_xlsx)
    salary_cols = ["Fixe_Annuel_MAD", "Min", "Mid", "Max", "Market_Median", "Cout_Ajustement"]

    with pd.ExcelWriter(path_xlsx, engine="openpyxl") as xw:
        # La priorité suit le score, pas l'ordre alphabétique des libellés (Info avant Major).
        df_sorted = df.sort_values("RiskScore", ascending=False)
        df_sorted.to_excel(xw, sheet_name="All", index=False)
        for sev in ["Critical", "Major", "Minor", "Info"]:
            sub = df[df["Severity"] == sev].sort_values("RiskScore", ascending=False)
            if sub.empty:
                sub = df.head(0).copy()
            sub.to_excel(xw, sheet_name=sev, index=False)

        # Synthèse budgétaire (Cout_Ajustement par Entite_N1 et Severity), calculée directement
        # sur la colonne numérique (plus de parsing de texte locale-dépendant).
        if "Cout_Ajustement" in df.columns:
            grp_cols = [c for c in ["Severity", "Entite_N1"] if c in df.columns]
            # Pourquoi (correction) : avant, les coûts arrivaient ici sous forme de texte mis en forme
            # ("12 345,67", avec des espaces insécables selon Windows). La conversion en nombre échouait
            # souvent : la synthèse budgétaire affichait des totaux faux.
            cout_num = pd.to_numeric(df["Cout_Ajustement"], errors="coerce")
            synth = (
                df.assign(_Cout_num=cout_num)
                  .groupby(grp_cols, dropna=False)["_Cout_num"]
                  .sum()
                  .reset_index()
                  .rename(columns={"_Cout_num": "Cout_Ajustement"})
                  .sort_values(["Severity", "Cout_Ajustement"], ascending=[True, False])
            )
            total = synth["Cout_Ajustement"].sum()
            if len(grp_cols) == 2:
                synth.loc[len(synth)] = ["TOTAL", "", total]
            else:
                synth.loc[len(synth)] = ["TOTAL", total]
            synth.to_excel(xw, sheet_name="Budget_Synthese", index=False)

        # Statistiques globales
        stats = {
            # Pourquoi ce libellé : l'ancien "Total anomalies" comptait en réalité TOUS les salariés
            # analysés (y compris ceux classés Info), ce qui laissait croire à autant d'anomalies.
            "Total salariés analysés": len(df),
            "Critical": (df["Severity"] == "Critical").sum(),
            "Major": (df["Severity"] == "Major").sum(),
            "Minor": (df["Severity"] == "Minor").sum(),
            "Info": (df["Severity"] == "Info").sum(),
            "Total adjustment cost": pd.to_numeric(df["Cout_Ajustement"], errors="coerce").sum(),
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
        # Coloration conditionnelle sur RiskScore (uniquement si la feuille a des lignes de
        # données : une feuille de sévérité vide - ex. aucun "Critical" - donne max_row=1 et
        # produirait une plage invalide "X2:X1").
        if "RiskScore" in header and max_row >= 2:
            col_idx = header.index("RiskScore") + 1
            rng = openpyxl.utils.get_column_letter(col_idx) + "2:" + openpyxl.utils.get_column_letter(col_idx) + str(max_row)
            rule = ColorScaleRule(start_type="num", start_value=0, start_color="63BE7B",
                                  mid_type="num", mid_value=50, mid_color="FFEB84",
                                  end_type="num", end_value=100, end_color="F8696B")
            ws.conditional_formatting.add(rng, rule)
        # Format numérique "milliers" pour les colonnes de salaire (Excel applique le séparateur
        # selon sa propre locale d'affichage ; les cellules restent numériques et filtrables).
        for name in salary_cols:
            if name in header:
                col_idx = header.index(name) + 1
                col_letter = openpyxl.utils.get_column_letter(col_idx)
                for row in range(2, max_row + 1):
                    ws[f"{col_letter}{row}"].number_format = "#,##0.00"
        # Ajuster la largeur des colonnes
        for i, name in enumerate(header, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(40, max(12, len(str(name)) + 2))

    # Add only severity breakdown pie chart to Statistics sheet
    #
    # Reperage dynamique des lignes Critical/Major/Minor/Info (plutot que des numeros de ligne
    # codes en dur, min_row=2/max_row=5). Avec l'ordre du dict stats (Total anomalies, Critical,
    # Major, Minor, Info, Total adjustment cost), ces numeros fixes visaient en fait les lignes
    # Total anomalies + Critical + Major + Minor : le graphique "repartition par severite"
    # incluait par erreur le total (une valeur qui n'est pas une categorie) et n'affichait jamais
    # Info. Chercher les lignes par leur libelle rend en plus le graphique robuste si l'ordre ou le
    # contenu du dict stats change plus tard.
    if "Statistics" in wb.sheetnames:
        ws = wb["Statistics"]
        metric_col = [cell.value for cell in ws["A"]]
        sev_rows = [i + 1 for i, v in enumerate(metric_col) if v in ("Critical", "Major", "Minor", "Info")]
        if sev_rows:
            min_r, max_r = min(sev_rows), max(sev_rows)
            pie = PieChart()
            pie.title = "Severity Breakdown"
            pie_data = Reference(ws, min_col=2, min_row=min_r, max_row=max_r)
            pie_labels = Reference(ws, min_col=1, min_row=min_r, max_row=max_r)
            pie.add_data(pie_data, titles_from_data=False)
            pie.set_categories(pie_labels)
            ws.add_chart(pie, "D2")
    wb.save(path_xlsx)
