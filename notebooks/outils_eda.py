#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
OUTILS DU NOTEBOOK « EDA_Salaire_ou_Compa_Ratio »
=============================================================

Ce fichier contient la « tuyauterie » du notebook : lire les trois fichiers Excel, dessiner les graphes,
écrire les constats et lancer les modèles. Il doit rester dans le même dossier que le notebook.

Pourquoi un fichier à part : le notebook ne garde ainsi que ce qu'on a besoin de lire et de régler
(les ratios, les contrôles, le traitement, la liste des colonnes et des modèles). Tout ce qui est
ici se lit seulement si on veut savoir comment un graphe est dessiné ou comment un chiffre est calculé.

Rien n'est calculé à l'import : chaque fonction est appelée par le notebook, avec ses données.
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from IPython.display import Markdown, display
from plotly.subplots import make_subplots
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

# Les trois statuts d'une ligne, et leur couleur dans les graphes
NORMAL, EXTREME, ERREUR = 'Normal', 'Valeur extrême', 'Erreur de données'
COULEURS = {NORMAL: 'steelblue', EXTREME: 'darkorange', ERREUR: 'crimson'}

# Le métier et le niveau servent à retrouver la grille et le marché de chaque salarié
CLES = ['Job_Family', 'Niveau']
# Les colonnes sans lesquelles le notebook ne peut pas tourner. Les autres (Entite_N1, Competence_N1, Hot_job,
# Positionnement_9BOX...) sont facultatives : si elles manquent, les graphes et les modèles font sans elles.
OBLIGATOIRES = {'employes.xlsx': ['Matricule', 'Job_Family', 'Niveau', 'Fixe_Annuel_MAD', 'Age', 'Anciennete'],
                'bands.xlsx': ['Job_Family', 'Niveau', 'Min', 'Mid', 'Max'],
                'market.xlsx': ['Job_Family', 'Niveau', 'Median']}

# scrollZoom : la molette zoome directement. toImageButtonOptions : l'appareil photo enregistre une image 2 fois plus fine.
CONFIG = {'scrollZoom': True, 'displaylogo': False, 'toImageButtonOptions': {'format': 'png', 'scale': 2}}

# Les six catégories du 9-Box, de la meilleure à celle qui demande une décision (le même ordre que dans src/anomaly_pretraitement.py)
ORDRE_9BOX = ['Hauts Potentiels', 'Talents', 'Performers', 'A repositionner', 'A développer', 'Décisions requises']

# Les 5 paquets qui servent à juger les modèles, toujours les mêmes d'un lancement à l'autre (random_state) :
# les résultats ne changent pas si on relance
PAQUETS = KFold(n_splits=5, shuffle=True, random_state=0)


# ---------------------------------------------------------------------------------------------------
# Écrire
# ---------------------------------------------------------------------------------------------------

def fr(x, decimales=2):
    """Un nombre écrit à la française : 0,93 et non 0.93."""
    texte = f"{x:.{decimales}f}"
    # Un tout petit nombre négatif s'arrondit en « -0,00 » : on écrit « 0,00 »
    return (texte.lstrip('-') if float(texte) == 0 else texte).replace('.', ',')


def part(n, total):
    """La part de n dans total, en % : « 2,5 % »."""
    return f"{fr(n / total * 100, 1)} %" if total else '0 %'


def constat(*phrases):
    """Écrit sous un tableau ou un graphe ce que disent les chiffres du fichier chargé.

    Ces phrases sont recalculées à chaque lancement : elles restent justes quand les données changent.
    """
    display(Markdown('> **Constat.** ' + ' '.join(p for p in phrases if p)))


def montrer(fig, hauteur=750):
    """Affiche le graphe en grand, avec la légende en dessous (à droite, elle prendrait de la largeur)."""
    # separators=', ' : les nombres des axes et du survol s'écrivent à la française (0,8 et 1 200), comme dans les constats
    fig.update_layout(template='plotly_white', height=hauteur, margin=dict(t=90, b=90), separators=', ',
                      legend=dict(orientation='h', x=0, y=-0.12, yanchor='top'))
    fig.show(config=CONFIG)


def infos_survol(df):
    """Les colonnes affichées quand la souris passe sur un salarié (seulement celles présentes dans le fichier)."""
    return [c for c in ['Matricule', 'Nom', 'Job_Title', 'Niveau', 'Fixe_Annuel_MAD'] if c in df.columns]


# ---------------------------------------------------------------------------------------------------
# Étape 1 : lire les trois fichiers et les croiser
# ---------------------------------------------------------------------------------------------------

def diviser(haut, bas):
    """Une division qui laisse vide quand le bas est vide, nul ou négatif, au lieu de donner un chiffre absurde."""
    return haut / bas.where(bas > 0)


def lire_et_croiser():
    """Lit employes.xlsx, bands.xlsx et market.xlsx, et rend un tableau : une ligne par salarié, avec sa grille et son marché."""
    # Les trois fichiers sont cherchés dans le dossier courant, puis dans input/ du projet
    # (le .bat ouvre le notebook depuis notebooks/)
    dossiers_possibles = [Path.cwd(), Path.cwd() / 'input', *[p / 'input' for p in Path.cwd().parents]]
    dossier = next((d for d in dossiers_possibles if (d / 'employes.xlsx').is_file()), None)
    if dossier is None:
        raise FileNotFoundError(f"employes.xlsx introuvable : ni dans {Path.cwd()}, ni dans un dossier input/ du projet.")
    print(f"Fichiers lus dans : {dossier}")

    tables = {}
    for fichier, attendues in OBLIGATOIRES.items():
        tables[fichier] = pd.read_excel(dossier / fichier)
        manquantes = [c for c in attendues if c not in tables[fichier].columns]
        if manquantes:
            raise ValueError(f"{fichier} : colonnes introuvables {manquantes}. Colonnes lues : {list(tables[fichier].columns)}. "
                             "Renommer les colonnes du fichier pour qu'elles portent exactement ces noms.")
    emp = tables['employes.xlsx']
    bands = tables['bands.xlsx'][OBLIGATOIRES['bands.xlsx']].copy()
    market = tables['market.xlsx'][OBLIGATOIRES['market.xlsx']].copy()

    # Le métier et le niveau doivent être écrits pareil dans les trois fichiers.
    # Métier : sans espaces autour. Niveau : en nombre si c'est possible partout, sinon en texte partout
    # (un « 5 » nombre d'un côté et un « 5 » texte de l'autre ne se retrouveraient pas).
    niveau_en_nombre = all(pd.to_numeric(t['Niveau'], errors='coerce').notna().equals(t['Niveau'].notna()) for t in (emp, bands, market))
    for t in (emp, bands, market):
        t['Job_Family'] = t['Job_Family'].where(t['Job_Family'].isna(), t['Job_Family'].astype(str).str.strip())
        t['Niveau'] = pd.to_numeric(t['Niveau']) if niveau_en_nombre else t['Niveau'].where(t['Niveau'].isna(), t['Niveau'].astype(str).str.strip())
        # Un salaire, un âge ou un Mid écrit en texte dans Excel (« 12 000 », « n.c. ») ne se calcule pas : il devient un nombre, ou reste vide
        for c in ['Fixe_Annuel_MAD', 'Age', 'Anciennete', 'Min', 'Mid', 'Max', 'Median']:
            if c in t.columns and not pd.api.types.is_numeric_dtype(t[c]):
                illisibles = int((pd.to_numeric(t[c], errors='coerce').isna() & t[c].notna()).sum())
                print(f"Colonne {c} écrite en texte : convertie en nombre ({illisibles} valeurs illisibles laissées vides).")
                t[c] = pd.to_numeric(t[c], errors='coerce')

    # Un matricule présent deux fois : on garde la première ligne
    nb_lignes = len(emp)
    emp = emp.drop_duplicates(subset=['Matricule'], keep='first').copy()
    print(f"Salariés : {nb_lignes} lignes lues, {len(emp)} gardées ({nb_lignes - len(emp)} doublons de matricule écartés).")
    # Un même métier + niveau présent deux fois dans la grille ou le marché : on garde le premier.
    # Sinon chaque salarié concerné serait recopié deux fois dans le tableau.
    for nom, t in [('bands.xlsx', bands), ('market.xlsx', market)]:
        en_double = int(t.duplicated(subset=CLES).sum())
        if en_double:
            print(f"{nom} : {en_double} lignes en double pour un même métier + niveau, la première est gardée.")
    bands, market = bands.drop_duplicates(subset=CLES), market.drop_duplicates(subset=CLES)

    # how='left' : on garde tous les salariés, même ceux dont le métier + niveau n'existe pas dans la grille ou le marché
    return emp.merge(bands, on=CLES, how='left').merge(market, on=CLES, how='left')


def constat_depart(df):
    """Combien de salariés, combien sans grille ou sans marché, et une alerte si le salaire et la grille ne sont pas dans la même unité."""
    sans_grille, sans_marche = df['Mid'].isna(), df['Median'].isna()
    phrases = [f"{len(df)} salariés. Sans grille : {int(sans_grille.sum())} ({part(sans_grille.sum(), len(df))}). "
               f"Sans marché : {int(sans_marche.sum())} ({part(sans_marche.sum(), len(df))})."]
    if sans_grille.any():
        # Les métiers + niveaux les plus souvent introuvables dans bands.xlsx : souvent un nom écrit différemment d'un fichier à l'autre
        absents = df[sans_grille].groupby(CLES, dropna=False).size().sort_values(ascending=False).head(5)
        phrases.append("Métier + niveau le plus souvent introuvables dans bands.xlsx : "
                       + ', '.join(f"{m} / {n} ({k})" for (m, n), k in absents.items()) + ". Vérifier qu'ils sont écrits pareil dans les deux fichiers.")
    mediane = df['Compa_Ratio'].median()
    if pd.notna(mediane) and not 0.2 <= mediane <= 5:
        phrases.append(f"**Attention : le Compa-Ratio médian vaut {fr(mediane)}.** Le salaire et la grille ne sont sans doute pas dans la même unité "
                       "(l'un en dirhams, l'autre en milliers, ou l'un au mois et l'autre à l'année). À corriger avant de lire la suite.")
    constat(*phrases)


# ---------------------------------------------------------------------------------------------------
# Étapes 2 et 4 : voir les valeurs aberrantes, puis l'effet du traitement
# ---------------------------------------------------------------------------------------------------

def _statuts(donnees):
    # Après le traitement, la colonne Statut n'existe plus : toutes les lignes gardées sont « normales »
    return donnees['Statut'] if 'Statut' in donnees.columns else pd.Series(NORMAL, index=donnees.index)


def nuage_salaire_mid(donnees, limites, fig, colonne=1, legende=True):
    """Le salaire (vertical) face au Mid (horizontal), un point par salarié, colorié selon son statut."""
    statuts = _statuts(donnees)
    for statut in [NORMAL, EXTREME, ERREUR]:
        groupe = donnees[(statuts == statut) & donnees['Mid'].notna() & donnees['Fixe_Annuel_MAD'].notna()]
        if groupe.empty:
            continue
        # Scattergl : dessine vite, même avec des dizaines de milliers de points
        fig.add_trace(go.Scattergl(x=groupe['Mid'], y=groupe['Fixe_Annuel_MAD'], mode='markers', name=statut, legendgroup=statut,
                                   showlegend=legende, marker=dict(color=COULEURS[statut], size=5, opacity=0.35 if statut == NORMAL else 0.9),
                                   customdata=groupe[['Matricule', 'Niveau', 'Compa_Ratio']].values,
                                   hovertemplate='Matricule %{customdata[0]} (niveau %{customdata[1]})<br>Mid : %{x:,.0f}<br>Salaire : %{y:,.0f}'
                                                 '<br>Compa-Ratio : %{customdata[2]:.2f}<extra></extra>'),
                      row=1, col=colonne)
    # Les trois lignes de repère, tracées d'un bout à l'autre des Mid
    bouts = np.array([donnees['Mid'].min(), donnees['Mid'].max()])
    for pente, nom, trait in [(1, 'Salaire = Mid', dict(color='black', width=2)),
                              (limites[0], f'Limite basse (Compa-Ratio {fr(limites[0])})', dict(color='gray', width=1.5, dash='dash')),
                              (limites[1], f'Limite haute (Compa-Ratio {fr(limites[1])})', dict(color='gray', width=1.5, dash='dot'))]:
        fig.add_trace(go.Scatter(x=bouts, y=bouts * pente, mode='lines', name=nom, legendgroup=nom, showlegend=legende,
                                 line=trait, hoverinfo='skip'), row=1, col=colonne)
    fig.update_xaxes(title_text='Mid (milieu de la grille)', row=1, col=colonne)


def repartition_compa(donnees, limites, fig, ligne=1, couleur='steelblue', nom='Salariés'):
    """Barres : combien de salariés pour chaque valeur du Compa-Ratio, avec les deux limites en pointillés."""
    # On fixe la largeur des barres (0,02) pour que deux graphes dessinés avec des données différentes restent comparables barre à barre
    fig.add_trace(go.Histogram(x=donnees['Compa_Ratio'].dropna(), xbins=dict(size=0.02), marker_color=couleur, opacity=0.75, name=nom,
                               hovertemplate='Compa-Ratio %{x} : %{y} salariés<extra></extra>'), row=ligne, col=1)
    for x, texte in [(limites[0], f'Limite basse {fr(limites[0])}'), (limites[1], f'Limite haute {fr(limites[1])}')]:
        fig.add_vline(x=x, line=dict(color='gray', dash='dash', width=2), annotation_text=texte, annotation_position='top', row=ligne, col=1)
    fig.add_vline(x=1, line=dict(color='black', width=1.5), row=ligne, col=1)
    fig.update_yaxes(title_text='Nombre de salariés', row=ligne, col=1)


def graphe_salaire_mid(df, limites):
    """Le grand nuage salaire / Mid, puis son constat : la corrélation, et la fourchette de salaire à Mid égal."""
    fig = make_subplots(rows=1, cols=1)
    nuage_salaire_mid(df, limites, fig)
    fig.update_yaxes(title_text='Fixe_Annuel_MAD (salaire)')
    fig.update_layout(title='Le salaire face au milieu de sa grille : chaque point est un salarié')
    montrer(fig, hauteur=800)

    lisibles = df[(_statuts(df) != ERREUR) & df['Compa_Ratio'].notna()]
    if len(lisibles) > 2:
        p5, p95 = lisibles['Compa_Ratio'].quantile(0.05), lisibles['Compa_Ratio'].quantile(0.95)
        constat(f"Corrélation salaire / Mid : {fr(lisibles['Fixe_Annuel_MAD'].corr(lisibles['Mid']))} (Pearson, sur les valeurs), "
                f"{fr(lisibles['Fixe_Annuel_MAD'].corr(lisibles['Mid'], method='spearman'))} (Spearman, sur le classement).",
                f"À Mid égal, 9 salariés sur 10 gagnent entre {fr(p5 * 100, 0)} % et {fr(p95 * 100, 0)} % de leur Mid : "
                f"pour un Mid de 100, le salaire va de {fr(p5 * 100, 0)} à {fr(p95 * 100, 0)}.")


def graphe_repartition(df, limites):
    """La répartition du Compa-Ratio (barres, et boîte à moustaches dessous), puis son constat."""
    sans_erreur = df[_statuts(df) != ERREUR]
    fig = make_subplots(rows=2, cols=1, row_heights=[0.78, 0.22], shared_xaxes=True, vertical_spacing=0.04)
    repartition_compa(sans_erreur, limites, fig)
    # La boîte sous les barres : chaque point isolé est un salarié, son matricule s'affiche au survol
    for trace in px.box(sans_erreur, x='Compa_Ratio', points='outliers', hover_data=infos_survol(df), color_discrete_sequence=['steelblue']).data:
        fig.add_trace(trace.update(showlegend=False), row=2, col=1)
    fig.update_yaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(title_text='Compa-Ratio (salaire / Mid) ; la ligne noire est à 1,00, le milieu de la grille', row=2, col=1)
    fig.update_layout(title='Répartition du Compa-Ratio, avec les limites des valeurs extrêmes', showlegend=False)
    montrer(fig, hauteur=750)

    avec_grille = sans_erreur[sans_erreur['Compa_Ratio'].notna()]
    sous_min, sur_max = (avec_grille['Fixe_Annuel_MAD'] < avec_grille['Min']).sum(), (avec_grille['Fixe_Annuel_MAD'] > avec_grille['Max']).sum()
    trop_bas, trop_haut = (avec_grille['Compa_Ratio'] < limites[0]).sum(), (avec_grille['Compa_Ratio'] > limites[1]).sum()
    constat(f"Sur {len(avec_grille)} salariés avec une grille : {int(sous_min)} sous le Min de leur grille ({part(sous_min, len(avec_grille))}), "
            f"{int(sur_max)} au-dessus du Max ({part(sur_max, len(avec_grille))}).",
            f"Valeurs extrêmes : {int(trop_bas)} sous la limite basse ({fr(limites[0])}), {int(trop_haut)} au-dessus de la limite haute ({fr(limites[1])}).")


def tableau_extremes(df, colonnes=('Fixe_Annuel_MAD', 'Age', 'Anciennete', 'Age_Embauche', 'Competence_N1', 'Range_Penetration', 'Market_Ratio')):
    """Pour chaque colonne chiffrée : les limites des moustaches (règle habituelle, 1,5) et combien de salariés sont au-delà."""
    lignes = []
    for colonne in colonnes:
        if colonne not in df.columns or not pd.api.types.is_numeric_dtype(df[colonne]) or df[colonne].notna().sum() == 0:
            continue
        valeurs = df[colonne].dropna()
        a, b = valeurs.quantile(0.25), valeurs.quantile(0.75)
        bas, haut = a - 1.5 * (b - a), b + 1.5 * (b - a)
        sous, sur = int((valeurs < bas).sum()), int((valeurs > haut).sum())
        lignes.append({'Colonne': colonne, 'Salariés': len(valeurs), 'Limite basse': round(bas, 2), 'Limite haute': round(haut, 2),
                       'Sous la limite basse': sous, 'Au-dessus de la limite haute': sur,
                       '% au-delà des limites': round((sous + sur) / len(valeurs) * 100, 1)})
    display(pd.DataFrame(lignes).set_index('Colonne'))


def graphes_avant_apres(df_avant, df_apres, limites):
    """Les deux graphes de l'étape 2, avant et après traitement, sur les mêmes échelles."""
    # 1. Le nuage salaire / Mid, côte à côte
    fig = make_subplots(rows=1, cols=2, shared_xaxes=True, shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=[f'Avant : {len(df_avant)} salariés', f'Après : {len(df_apres)} salariés'])
    nuage_salaire_mid(df_avant, limites, fig, colonne=1)
    nuage_salaire_mid(df_apres, limites, fig, colonne=2, legende=False)
    fig.update_yaxes(title_text='Fixe_Annuel_MAD (salaire)', row=1, col=1)
    fig.update_layout(title='Le salaire face au milieu de sa grille, avant et après traitement')
    montrer(fig, hauteur=750)

    # 2. La répartition du Compa-Ratio, avant (en haut) et après (en bas), sur le même axe
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=['Avant', 'Après'])
    repartition_compa(df_avant[_statuts(df_avant) != ERREUR], limites, fig, ligne=1, couleur='darkorange', nom='Avant')
    repartition_compa(df_apres, limites, fig, ligne=2, couleur='steelblue', nom='Après')
    fig.update_xaxes(title_text='Compa-Ratio (salaire / Mid)', row=2, col=1)
    fig.update_layout(title='Répartition du Compa-Ratio, avant et après traitement', showlegend=False)
    montrer(fig, hauteur=750)


def chiffres_compa(donnees):
    """Les chiffres qui résument le Compa-Ratio et son lien avec le Mid, pour le tableau avant / après."""
    c = donnees['Compa_Ratio'].dropna()
    return {'Salariés': len(donnees), 'Compa-Ratio : moyenne': c.mean(), 'Compa-Ratio : médiane': c.median(),
            'Compa-Ratio : écart-type (étalement)': c.std(), 'Compa-Ratio : minimum': c.min(), 'Compa-Ratio : maximum': c.max(),
            "Compa-Ratio : asymétrie (0 = autant à gauche qu'à droite)": c.skew(),
            'Lien salaire / Mid (Pearson)': donnees['Fixe_Annuel_MAD'].corr(donnees['Mid']),
            'Lien salaire / Mid (Spearman)': donnees['Fixe_Annuel_MAD'].corr(donnees['Mid'], method='spearman')}


def constat_avant_apres(comparaison, nb_ecartes, nb_avant):
    """Ce que le traitement a changé, en une phrase par chiffre."""
    if nb_ecartes == 0:
        return constat("Aucune ligne mise de côté : avant et après sont identiques.")
    avant, apres = comparaison['Avant'], comparaison['Après']
    constat(f"{nb_ecartes} lignes mises de côté sur {nb_avant} ({part(nb_ecartes, nb_avant)}).",
            f"Écart-type du Compa-Ratio : de {fr(avant['Compa-Ratio : écart-type (étalement)'], 3)} à {fr(apres['Compa-Ratio : écart-type (étalement)'], 3)}.",
            f"Médiane : de {fr(avant['Compa-Ratio : médiane'], 3)} à {fr(apres['Compa-Ratio : médiane'], 3)}.",
            f"Lien salaire / Mid (Pearson) : de {fr(avant['Lien salaire / Mid (Pearson)'], 3)} à {fr(apres['Lien salaire / Mid (Pearson)'], 3)}.")


# ---------------------------------------------------------------------------------------------------
# Étape 5 : les matrices de corrélation
# ---------------------------------------------------------------------------------------------------

def en_nombres(df):
    """Une copie du tableau pour les matrices, où le 9-Box écrit en mots devient un rang (6 = Hauts Potentiels ... 1 = Décisions requises)."""
    df_num = df.copy()
    if 'Positionnement_9BOX' in df_num and not pd.api.types.is_numeric_dtype(df_num['Positionnement_9BOX']):
        rangs = {nom.casefold(): len(ORDRE_9BOX) - i for i, nom in enumerate(ORDRE_9BOX)}
        # On compare en minuscules et sans espaces autour, pour qu'un « talents » ou un « Talents » comptent pareil
        libelles = df_num['Positionnement_9BOX'].astype('string').str.strip().str.casefold()
        inconnus = sorted(df_num.loc[libelles.notna() & ~libelles.isin(list(rangs)), 'Positionnement_9BOX'].unique())
        if inconnus:
            print(f"Catégories 9-Box non reconnues, laissées vides dans les matrices : {inconnus}")
        df_num['Positionnement_9BOX'] = libelles.map(rangs).astype(float)
    return df_num


# Les messages déjà affichés : une même colonne laissée de côté n'est signalée qu'une fois, pas sous chaque matrice
_deja_dit = set()


def _dire_une_fois(message):
    if message not in _deja_dit:
        _deja_dit.add(message)
        print(message)


def utilisables(df_num, colonnes):
    """Garde les colonnes présentes, chiffrées et qui varient ; dit lesquelles sont laissées de côté."""
    presentes = [c for c in colonnes if c in df_num.columns and pd.api.types.is_numeric_dtype(df_num[c]) and df_num[c].notna().any()]
    for c in colonnes:
        if c not in presentes:
            _dire_une_fois(f"Colonne {c} : absente, vide ou écrite en mots, laissée hors des matrices.")
    # Une colonne qui a la même valeur pour tout le monde ne « bouge » pas : son lien avec les autres ne se calcule pas.
    # On arrondit au millième, pour qu'un écart de calcul invisible (0,5000000001) ne passe pas pour une vraie différence.
    gardees = [c for c in presentes if df_num[c].round(3).nunique() > 1]
    for c in presentes:
        if c not in gardees:
            _dire_une_fois(f"Colonne {c} : la même valeur pour tous les salariés, laissée hors des matrices et des modèles.")
    return gardees


def matrice(df_num, colonnes, titre):
    """La matrice de corrélation (Pearson, le calcul du notebook du comité) des colonnes demandées."""
    colonnes = utilisables(df_num, colonnes)
    liens = df_num[colonnes].corr()
    # RdBu_r : bleu pour les liens négatifs, rouge pour les positifs, blanc autour de 0
    fig = go.Figure(go.Heatmap(z=liens.values, x=colonnes, y=colonnes, zmin=-1, zmax=1, colorscale='RdBu_r', texttemplate='%{z:.2f}',
                               colorbar=dict(title='Lien'), hovertemplate='%{y} / %{x}<br><b>%{z:.2f}</b><extra></extra>'))
    # La première colonne en haut, comme un tableau qu'on lit de haut en bas
    fig.update_yaxes(autorange='reversed')
    fig.update_layout(title=titre)
    montrer(fig, hauteur=850)


def constat_liens(df_num, cible, colonnes, a_ignorer=(), repetitions=False):
    """Les colonnes les plus liées à la cible, celles qui se répètent, et celles dont le chiffre tient à quelques salariés extrêmes."""
    colonnes = [c for c in utilisables(df_num, colonnes) if c != cible and c not in a_ignorer]
    if cible not in df_num.columns or not colonnes:
        return
    pearson = df_num[colonnes].corrwith(df_num[cible]).dropna()
    ordre = pearson.abs().sort_values(ascending=False).index
    phrases = [f"Colonnes les plus liées à {cible} : " + ', '.join(f"{c} ({fr(pearson[c])})" for c in ordre[:3]) + '.',
               f"La moins liée : {ordre[-1]} ({fr(pearson[ordre[-1]])})."]
    if pearson.abs().max() < 0.10:
        phrases.append("Aucune ne dépasse 0,10 : aucun lien en ligne droite ne se voit.")
    # Le même calcul sur le classement (Spearman) : s'il donne un chiffre très différent, la corrélation affichée
    # tient à quelques salariés extrêmes, et il vaut mieux la lire avec prudence
    spearman = df_num[colonnes].corrwith(df_num[cible], method='spearman').reindex(pearson.index)
    fragiles = [c for c in ordre if abs(pearson[c] - spearman[c]) > 0.10]
    if fragiles:
        phrases.append("À lire avec prudence, le chiffre change beaucoup quand on regarde seulement le classement : "
                       + ', '.join(f"{c} ({fr(pearson[c])} devient {fr(spearman[c])})" for c in fragiles) + '.')
    if repetitions:
        # Deux colonnes explicatives liées à plus de 0,8 disent presque la même chose : le modèle n'a besoin que d'une des deux
        liens = df_num[colonnes].corr()
        paires = [f"{a} / {b} ({fr(liens.loc[a, b])})" for i, a in enumerate(colonnes) for b in colonnes[i + 1:] if abs(liens.loc[a, b]) > 0.8]
        phrases.append("Colonnes qui se répètent (lien au-dessus de 0,8) : " + ', '.join(paires) + '.' if paires
                       else "Aucune paire de colonnes explicatives n'est liée à plus de 0,8.")
    constat(*phrases)


# ---------------------------------------------------------------------------------------------------
# Étape 6 : les modèles
# ---------------------------------------------------------------------------------------------------

def tableau_modele(base, colonnes_modele):
    """Le tableau donné aux modèles : les colonnes déclarées, présentes et qui varient ; les catégories écrites en texte."""
    def varie(colonne):
        valeurs = base[colonne].round(3) if pd.api.types.is_numeric_dtype(base[colonne]) else base[colonne]
        return valeurs.nunique(dropna=True) > 1

    colonnes = [c for c in colonnes_modele if c in base.columns and varie(c)]
    ecartees = [c for c in colonnes_modele if c not in colonnes]
    if ecartees:
        print(f"Colonnes absentes ou identiques pour tous, non données aux modèles : {ecartees}")
    X = base[colonnes].copy()
    for c in colonnes:
        # Une colonne déclarée « nombre » mais écrite en mots est prise en catégorie.
        # Une case vide devient la catégorie « Inconnu » : le salarié reste dans le calcul.
        if colonnes_modele[c] == 'catégorie' or not pd.api.types.is_numeric_dtype(X[c]):
            X[c] = X[c].astype('string').fillna('Inconnu').astype(str)
    return X


def predire(methode, X, y):
    """Le salaire (ou le Compa-Ratio) de chaque salarié, prédit par un modèle qui ne l'a jamais vu.

    methode : 'regression' (une addition d'effets) ou 'arbres' (des groupes par questions successives).
    Les salariés sont coupés en 5 paquets : le modèle apprend sur 4 et prédit le 5ᵉ, et on tourne.
    """
    categories = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    nombres = [c for c in X.columns if c not in categories]
    # Nombres : une case vide prend la valeur médiane de la colonne. Catégories : une colonne 0/1 par valeur.
    preparation = ColumnTransformer([('nombres', SimpleImputer(strategy='median'), nombres),
                                     ('categories', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categories)])
    modele = LinearRegression() if methode == 'regression' else HistGradientBoostingRegressor(random_state=0)
    with warnings.catch_warnings():
        # Un métier rare peut être absent d'un des 5 paquets d'apprentissage : le modèle l'ignore et sklearn le signale, sans gravité
        warnings.simplefilter('ignore')
        return cross_val_predict(make_pipeline(preparation, modele), X, y, cv=PAQUETS)


def juger(predictions, salaire, mid):
    """Le tableau des erreurs de chaque modèle, toutes mesurées sur le salaire."""
    return pd.DataFrame({nom: {
        'Erreur moyenne (MAE)': mean_absolute_error(salaire, p),
        'Erreur qui punit les gros écarts (RMSE)': root_mean_squared_error(salaire, p),
        'Erreur médiane en %': np.median(np.abs(p / salaire - 1)) * 100,
        'R² sur le salaire': r2_score(salaire, p),
        'R² sur le Compa-Ratio': r2_score(salaire / mid, p / mid),
    } for nom, p in predictions.items()}).T


def constat_modeles(predictions, resultats, salaire):
    """Le meilleur modèle, ceux qu'on ne peut pas départager de lui, et ce qu'il explique."""
    # De combien l'erreur d'un même modèle bouge d'un paquet à l'autre : c'est la marge en dessous de laquelle
    # un écart entre deux modèles ne veut rien dire (il tient au tirage des paquets)
    paquet = np.empty(len(salaire), dtype=int)
    for k, (_, test) in enumerate(PAQUETS.split(salaire)):
        paquet[test] = k
    marge = np.mean([np.std([np.median(np.abs(p[paquet == k] / salaire[paquet == k] - 1)) * 100 for k in range(PAQUETS.n_splits)])
                     for p in predictions.values()])
    erreurs = resultats['Erreur médiane en %']
    meilleur, pire = erreurs.idxmin(), erreurs.idxmax()
    proches = [nom for nom in erreurs.index if nom != meilleur and erreurs[nom] - erreurs[meilleur] <= marge]
    r2_salaire, r2_compa = resultats.loc[meilleur, 'R² sur le salaire'], resultats.loc[meilleur, 'R² sur le Compa-Ratio']
    constat(f"Plus petite erreur médiane : « {meilleur} » ({fr(erreurs[meilleur], 1)} %). Plus grande : « {pire} » ({fr(erreurs[pire], 1)} %).",
            f"D'un paquet à l'autre, l'erreur d'un même modèle bouge d'environ {fr(marge, 1)} %.",
            ("À cette marge près, on ne peut pas départager le meilleur de : " + ', '.join(f'« {n} »' for n in proches) + '.') if proches
            else "Aucun autre modèle n'est aussi proche : l'écart avec le meilleur est réel.",
            f"« {meilleur} » explique {fr(max(r2_salaire, 0) * 100, 0)} % des écarts de salaire et {fr(max(r2_compa, 0) * 100, 0)} % des écarts autour du Mid.")
