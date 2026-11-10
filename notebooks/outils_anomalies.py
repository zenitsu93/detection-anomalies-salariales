#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
OUTILS DU NOTEBOOK « Comparaison_Modeles_Anomalies »
====================================================

Ce fichier contient la « tuyauterie » du notebook : lancer chaque modèle de détection, compter qui est
signalé, fabriquer des anomalies connues pour le test, dessiner les graphes et écrire les constats.
Il doit rester dans le même dossier que le notebook, avec outils_eda.py (qui lit les trois fichiers Excel).

Pourquoi un fichier à part : le notebook ne garde ainsi que ce qu'on a besoin de lire et de régler
(la liste des modèles, les colonnes qu'ils regardent, la part de salariés signalés, le test).

Tous les modèles rendent la même chose : un score par salarié, d'autant plus grand que le salarié
ressort. C'est ce qui permet de les comparer : on prend pour chacun les salariés les mieux classés.

Rien n'est calculé à l'import : chaque fonction est appelée par le notebook, avec ses données.
"""

import contextlib
import io
import math
import time
import warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from IPython.display import display
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

import outils_eda as eda
# lire_et_croiser et constat_depart sont repris tels quels de outils_eda : le notebook n'a ainsi qu'un seul fichier à importer
from outils_eda import constat, constat_depart, fr, lire_et_croiser, montrer

# Les libellés de la performance N-1, du moins bon au meilleur (le même ordre que dans src/anomaly_pretraitement.py).
# Ils servent à donner un rang de 1 à 5, que les modèles savent lire.
ORDRE_PERFORMANCE = ["Très en dessous", "Proche de l'objectif", "A l'objectif", "Supérieur à l'objectif", "Très au-delà"]

# Les deux familles de modèles, et leur couleur dans les graphes
PROFIL, SALAIRE = 'Cherche un profil rare', 'Cherche un salaire trop bas'
FAMILLES = {
    'Isolation Forest': PROFIL,
    'Local Outlier Factor': PROFIL,
    'One-Class SVM': PROFIL,
    'Distance robuste': PROFIL,
    'Écart aux collègues': SALAIRE,
    'Salaire attendu, régression': SALAIRE,
    'Salaire attendu, arbres': SALAIRE,
}
COULEURS = {PROFIL: 'steelblue', SALAIRE: 'darkorange'}

# Les réglages des modèles. Ce sont les valeurs habituelles ; on peut les changer ici.
ARBRES_FORET = 200            # Isolation Forest : nombre de découpages au hasard (comme dans la détection du projet)
VOISINS = 20                  # Local Outlier Factor : à combien de voisins chaque salarié est comparé
PART_HORS_FRONTIERE = 0.05    # One-Class SVM : part des salariés que la frontière a le droit de laisser dehors
MAX_APPRENTISSAGE_SVM = 5000  # One-Class SVM : il apprend sur 5 000 salariés au plus (au-delà, il devient très lent), puis note tout le monde
GRAINE = 42                   # le hasard est fixé : mêmes scores à chaque lancement


# ---------------------------------------------------------------------------------------------------
# Préparer le tableau
# ---------------------------------------------------------------------------------------------------

def ajouter_ratios(df):
    """Calcule les ratios et le rang de la performance. Rend le même tableau, complété."""
    # eda.diviser laisse la case vide quand le dénominateur est vide, nul ou négatif
    df['Compa_Ratio'] = eda.diviser(df['Fixe_Annuel_MAD'], df['Mid'])
    df['Range_Penetration'] = eda.diviser(df['Fixe_Annuel_MAD'] - df['Min'], df['Max'] - df['Min'])
    df['Market_Ratio'] = eda.diviser(df['Fixe_Annuel_MAD'], df['Median'])
    df['Ratio_Grille_Marche'] = eda.diviser(df['Mid'], df['Median'])
    if 'Performance_N1' in df.columns:
        # On compare sans les espaces autour. Un libellé inconnu ou une case vide donne un rang vide.
        rangs = {libelle: i + 1 for i, libelle in enumerate(ORDRE_PERFORMANCE)}
        df['Rang_Performance'] = df['Performance_N1'].astype('string').str.strip().map(rangs).astype(float)
    return df


# Les messages déjà affichés : une colonne laissée de côté n'est signalée qu'une fois, pas à chaque modèle
_deja_dit = set()


def _dire_une_fois(message):
    if message not in _deja_dit:
        _deja_dit.add(message)
        print(message)


def tableau_profil(base, colonnes):
    """Le tableau que lisent les modèles « profil rare » : des nombres, sans case vide, tous à la même échelle."""
    gardees = []
    for c in colonnes:
        if c not in base.columns or not pd.api.types.is_numeric_dtype(base[c]) or base[c].notna().sum() == 0:
            _dire_une_fois(f"Colonne {c} : absente, vide ou écrite en mots, non donnée aux modèles « profil rare ».")
        elif base[c].round(3).nunique() <= 1:
            _dire_une_fois(f"Colonne {c} : la même valeur pour tous, non donnée aux modèles « profil rare ».")
        else:
            gardees.append(c)
    X = base[gardees].astype(float)
    # Le salaire est lu en logarithme : passer de 100 à 200 compte alors autant que de 1 000 à 2 000.
    # Sans cela, les quelques très hauts salaires seraient « loin de tout le monde » par leur seul montant.
    if 'Fixe_Annuel_MAD' in X:
        X['Fixe_Annuel_MAD'] = np.log(X['Fixe_Annuel_MAD'])
    # Une case vide prend la valeur du milieu de sa colonne (la médiane) : ces modèles ne savent pas lire une case vide
    X = X.fillna(X.median())
    # Même échelle pour toutes les colonnes (moyenne 0, écart-type 1). Pourquoi : trois de ces modèles mesurent des
    # distances entre salariés ; sans cela, l'âge (de 20 à 60) compterait bien plus que le Compa-Ratio (de 0,7 à 1,3).
    return pd.DataFrame(StandardScaler().fit_transform(X), index=X.index, columns=gardees)


# ---------------------------------------------------------------------------------------------------
# Les modèles : chacun rend un score par salarié, d'autant plus grand que le salarié ressort
# ---------------------------------------------------------------------------------------------------

def profil_rare(nom, base, colonnes):
    """Les quatre modèles qui cherchent un profil rare, toutes colonnes regardées d'un coup."""
    X = tableau_profil(base, colonnes)
    if nom == 'Isolation Forest':
        # Il découpe les salariés au hasard, encore et encore : un profil rare se retrouve seul en peu de découpes
        modele = IsolationForest(n_estimators=ARBRES_FORET, random_state=GRAINE).fit(X)
        score = -modele.score_samples(X)
    elif nom == 'Local Outlier Factor':
        # Il compare chaque salarié à ses plus proches voisins : un salarié isolé, là où ses voisins sont serrés, ressort
        modele = LocalOutlierFactor(n_neighbors=min(VOISINS, len(X) - 1)).fit(X)
        score = -modele.negative_outlier_factor_
    elif nom == 'One-Class SVM':
        # Il trace une frontière autour de la masse des salariés : plus on est loin dehors, plus le score est haut
        appris = X.sample(min(len(X), MAX_APPRENTISSAGE_SVM), random_state=GRAINE)
        modele = OneClassSVM(nu=PART_HORS_FRONTIERE, gamma='scale').fit(appris)
        score = -modele.score_samples(X)
    elif nom == 'Distance robuste':
        # Il mesure la distance au profil « du milieu », calculé sans les salariés les plus éloignés
        # (sinon ce sont eux qui déplaceraient le milieu)
        modele = EllipticEnvelope(random_state=GRAINE).fit(X)
        score = modele.mahalanobis(X)
    else:
        raise ValueError(f"Modèle inconnu : {nom}")
    return pd.Series(score, index=base.index)


def _ecart_robuste(valeurs, centre, etalement):
    """De combien d'écarts habituels une valeur est SOUS le centre (0 si elle est au niveau ou au-dessus)."""
    return (-(valeurs - centre) / etalement).clip(lower=0)


def ecart_collegues(base, taille_min):
    """Le Compa-Ratio de chaque salarié, comparé à celui de ses collègues de même métier et de même niveau.

    Si le groupe compte moins de taille_min personnes, on compare à tout le niveau, puis à tout le monde.
    Le centre est la médiane, et l'écart habituel vient des écarts médians : quelques salaires très à part
    ne les déplacent pas. On compare en logarithme : « 20 % de moins » pèse autant que « 20 % de plus ».
    """
    log = np.log(base['Compa_Ratio'])
    z = pd.Series(np.nan, index=base.index)
    for cles in (eda.CLES, ['Niveau'], []):
        if cles:
            groupes = [base[c] for c in cles]
            taille, centre = log.groupby(groupes).transform('size'), log.groupby(groupes).transform('median')
            etalement = 1.4826 * (log - centre).abs().groupby(groupes).transform('median')
        else:
            taille = pd.Series(len(log), index=log.index)
            centre = pd.Series(log.median(), index=log.index)
            etalement = pd.Series(1.4826 * (log - log.median()).abs().median(), index=log.index)
            taille_min = 0
        # Un groupe trop petit, ou dont tous les salaires sont identiques (écart habituel nul), passe au groupe plus large
        possible = z.isna() & (taille >= taille_min) & (etalement > 0)
        z[possible] = _ecart_robuste(log, centre, etalement)[possible]
    return z.fillna(0)


def sous_attendu(methode, base, colonnes_modele):
    """De combien le salaire est SOUS le salaire attendu pour le poste et le profil.

    Le salaire attendu de chaque salarié est prédit par un modèle qui ne l'a jamais vu (5 paquets : on
    apprend sur 4, on prédit le 5ᵉ). Pourquoi : un salaire anormal qui sert à apprendre tire le modèle
    vers lui et se cache. methode : 'regression' (une addition d'effets) ou 'arbres'.
    """
    # Le salaire et le Mid en logarithme : l'écart se lit alors en %, comparable d'un niveau à l'autre
    # tableau_modele dit quelles colonnes il laisse de côté : on retient son message pour ne l'afficher qu'une fois,
    # et non à chaque modèle et à chaque essai du test
    messages = io.StringIO()
    with contextlib.redirect_stdout(messages):
        X = eda.tableau_modele(base.assign(Mid=np.log(base['Mid'])), colonnes_modele)
    if messages.getvalue().strip():
        _dire_une_fois(messages.getvalue().strip().replace('non données aux modèles', 'non données aux modèles « salaire attendu »'))
    log_salaire = np.log(base['Fixe_Annuel_MAD'].to_numpy())
    ecart = pd.Series(log_salaire - eda.predire(methode, X, log_salaire), index=base.index)
    centre = ecart.median()
    etalement = 1.4826 * (ecart - centre).abs().median() or ecart.std() or 1.0
    return _ecart_robuste(ecart, centre, etalement)


def _score(nom, base, colonnes_profil, colonnes_attendu, taille_groupe):
    if nom == 'Écart aux collègues':
        return ecart_collegues(base, taille_groupe)
    if nom == 'Salaire attendu, régression':
        return sous_attendu('regression', base, colonnes_attendu)
    if nom == 'Salaire attendu, arbres':
        return sous_attendu('arbres', base, colonnes_attendu)
    return profil_rare(nom, base, colonnes_profil)


def lancer(modeles, base, colonnes_profil, colonnes_attendu, taille_groupe, silencieux=False):
    """Lance chaque modèle et rend le tableau des scores : une ligne par salarié, une colonne par modèle.

    Un modèle qui ne peut pas tourner sur ces données est laissé de côté, avec la raison : les autres continuent.
    """
    scores = {}
    for nom in modeles:
        debut = time.perf_counter()
        try:
            # Les avertissements techniques de sklearn sont tus : s'il y a un vrai problème, le modèle s'arrête et on le dit
            # En mode silencieux (le test, qui relance tout plusieurs fois), les messages des modèles ne sont pas réaffichés
            muet = contextlib.redirect_stdout(io.StringIO()) if silencieux else contextlib.nullcontext()
            with warnings.catch_warnings(), muet:
                warnings.simplefilter('ignore')
                score = _score(nom, base, colonnes_profil, colonnes_attendu, taille_groupe)
            if not np.isfinite(score).all():
                raise ValueError("des scores impossibles à calculer")
            scores[nom] = score
            if not silencieux:
                print(f"{nom} : fait en {fr(time.perf_counter() - debut, 1)} s")
        except Exception as erreur:
            _dire_une_fois(f"{nom} : n'a pas pu tourner sur ces données, laissé de côté ({erreur}).")
    if not scores:
        raise ValueError("Aucun modèle n'a pu tourner : vérifier les colonnes données aux modèles.")
    return pd.DataFrame(scores)


# ---------------------------------------------------------------------------------------------------
# Étape 3 : qui est signalé ?
# ---------------------------------------------------------------------------------------------------

def signales(scores, part_signalee):
    """Pour chaque modèle, True pour les salariés les mieux classés (la part demandée), False pour les autres."""
    combien = math.ceil(part_signalee * len(scores))
    # method='first' : exactement « combien » salariés, même en cas d'égalité.
    # s > s.min() : un salarié au score le plus bas (0 = « pas sous l'attendu ») n'est jamais signalé, même s'il reste de la place.
    return scores.apply(lambda s: (s.rank(ascending=False, method='first') <= combien) & (s > s.min()))


def tableau_signales(base, signes, seuil_compa_bas):
    """Pour chaque modèle : combien de signalés, et où ils sont dans leur grille. La dernière ligne : tous les salariés."""
    def resume(groupe):
        return {'Salariés': len(groupe),
                '% sous le Min': (groupe['Fixe_Annuel_MAD'] < groupe['Min']).mean() * 100,
                f'% Compa-Ratio sous {fr(seuil_compa_bas)}': (groupe['Compa_Ratio'] < seuil_compa_bas).mean() * 100,
                '% au-dessus du Max': (groupe['Fixe_Annuel_MAD'] > groupe['Max']).mean() * 100,
                'Compa-Ratio médian': groupe['Compa_Ratio'].median()}

    lignes = {nom: resume(base[signes[nom]]) for nom in signes.columns}
    lignes['Tous les salariés'] = resume(base)
    return pd.DataFrame(lignes).T


def graphe_signales(base, signes):
    """Une boîte par modèle : le Compa-Ratio de ses signalés. En bas, la boîte de tous les salariés, pour comparer."""
    fig = go.Figure()
    fig.add_trace(go.Box(x=base['Compa_Ratio'], name='Tous les salariés', marker_color='gray', boxpoints=False,
                         orientation='h', showlegend=False))
    deja = set()
    for nom in reversed(list(signes.columns)):
        famille = FAMILLES.get(nom, PROFIL)
        fig.add_trace(go.Box(x=base.loc[signes[nom], 'Compa_Ratio'], name=nom, marker_color=COULEURS[famille], boxpoints=False,
                             orientation='h', showlegend=False))
        deja.add(famille)
    # La légende : une entrée par famille (et non par modèle)
    for famille in [f for f in COULEURS if f in deja]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(color=COULEURS[famille], size=14, symbol='square'),
                                 name=famille))
    fig.add_vline(x=1, line=dict(color='black', width=1.5), annotation_text='Milieu de grille (1,00)', annotation_position='top')
    fig.update_xaxes(title_text='Compa-Ratio (salaire / Mid) des salariés signalés')
    # ticksuffix : un peu d'air entre le nom du modèle et sa boîte
    fig.update_yaxes(ticksuffix='  ')
    fig.update_layout(title='Où sont les salariés signalés dans leur grille ?')
    montrer(fig, hauteur=700)


def constat_signales(tableau, seuil_compa_bas):
    """Le modèle dont les signalés sont le plus souvent bas dans leur grille, et celui qui signale le plus de salaires au-dessus du Max."""
    modeles = tableau.drop(index='Tous les salariés')
    tous = tableau.loc['Tous les salariés']
    bas, haut = f'% Compa-Ratio sous {fr(seuil_compa_bas)}', '% au-dessus du Max'
    plus_bas, plus_haut = modeles[bas].idxmax(), modeles[haut].idxmax()
    phrases = [f"Chaque modèle signale {int(modeles['Salariés'].max())} salariés au plus.",
               f"Dans tout le fichier, {fr(tous[bas], 1)} % des salariés ont un Compa-Ratio sous {fr(seuil_compa_bas)} et "
               f"{fr(tous[haut], 1)} % sont au-dessus du Max.",
               f"Le modèle dont les signalés sont le plus souvent sous {fr(seuil_compa_bas)} : « {plus_bas} » ({fr(modeles.loc[plus_bas, bas], 1)} %). "
               f"Le moins souvent : « {modeles[bas].idxmin()} » ({fr(modeles[bas].min(), 1)} %)."]
    if modeles[haut].max() > 0:
        phrases.append(f"Celui qui signale le plus de salariés au-dessus du Max : « {plus_haut} » ({fr(modeles.loc[plus_haut, haut], 1)} % de ses signalés).")
    else:
        phrases.append("Aucun modèle ne signale de salarié au-dessus du Max.")
    constat(*phrases)


# ---------------------------------------------------------------------------------------------------
# Étape 4 : les modèles signalent-ils les mêmes salariés ?
# ---------------------------------------------------------------------------------------------------

def graphe_accord(signes):
    """Pour chaque paire de modèles : la part des signalés de la ligne que la colonne signale aussi. Puis le constat."""
    noms = list(signes.columns)
    commun = pd.DataFrame({b: {a: (signes[a] & signes[b]).sum() / max(signes[a].sum(), 1) * 100 for a in noms} for b in noms})
    fig = go.Figure(go.Heatmap(z=commun.values, x=noms, y=noms, zmin=0, zmax=100, colorscale='Blues', texttemplate='%{z:.0f} %',
                               colorbar=dict(title='En commun'),
                               hovertemplate='%{z:.0f} % des signalés de « %{y} »<br>sont aussi signalés par « %{x} »<extra></extra>'))
    # Le premier modèle en haut, comme un tableau qu'on lit de haut en bas
    fig.update_yaxes(autorange='reversed', ticksuffix='  ')
    fig.update_layout(title='Les modèles signalent-ils les mêmes salariés ? (part des signalés de la ligne aussi signalés par la colonne)')
    montrer(fig, hauteur=750)

    if len(noms) < 2:
        return
    paires = {(a, b): (commun.loc[a, b] + commun.loc[b, a]) / 2 for i, a in enumerate(noms) for b in noms[i + 1:]}
    proche, loin = max(paires, key=paires.get), min(paires, key=paires.get)
    combien = signes.sum(axis=1)
    constat(f"Les deux modèles les plus d'accord : « {proche[0]} » et « {proche[1]} » ({fr(paires[proche], 0)} % de signalés en commun). "
            f"Les moins d'accord : « {loin[0]} » et « {loin[1]} » ({fr(paires[loin], 0)} %).",
            f"{int((combien >= 1).sum())} salariés sont signalés par au moins un modèle, dont {int((combien == 1).sum())} par un seul "
            f"et {int((combien == len(noms)).sum())} par les {len(noms)}.")


# ---------------------------------------------------------------------------------------------------
# Étape 5 : le test avec des anomalies qu'on connaît
# ---------------------------------------------------------------------------------------------------

def fabriquer_anomalies(base, part_fabriquee, baisse, graine):
    """Une copie du tableau où une part des salariés, tirés au hasard, a un salaire baissé. Rend la copie et qui a été baissé."""
    hasard = np.random.default_rng(graine)
    choisis = hasard.choice(base.index.to_numpy(), size=max(1, round(part_fabriquee * len(base))), replace=False)
    essai = base.copy()
    # Chaque salarié choisi perd entre baisse[0] et baisse[1] de son salaire (0.12 = 12 %)
    essai.loc[choisis, 'Fixe_Annuel_MAD'] *= 1 - hasard.uniform(baisse[0], baisse[1], size=len(choisis))
    # Les ratios sont recalculés avec le nouveau salaire : les modèles ne doivent voir que le tableau modifié
    return ajouter_ratios(essai), essai.index.isin(choisis)


def tester(modeles, base, colonnes_profil, colonnes_attendu, taille_groupe, part_fabriquee, baisse, part_signalee, essais):
    """Refait le test « essais » fois, avec des salariés différents à chaque fois.

    Rend, pour chaque modèle et chaque essai, la part des anomalies fabriquées qu'il retrouve parmi ses signalés (en %).
    """
    resultats = {}
    for numero in range(1, essais + 1):
        debut = time.perf_counter()
        essai, fabriquees = fabriquer_anomalies(base, part_fabriquee, baisse, graine=numero)
        signes = signales(lancer(modeles, essai, colonnes_profil, colonnes_attendu, taille_groupe, silencieux=True), part_signalee)
        resultats[f'Essai {numero}'] = signes[fabriquees].mean() * 100
        print(f"Essai {numero} sur {essais} : {int(fabriquees.sum())} salaires baissés, fait en {fr(time.perf_counter() - debut, 0)} s")
    resultats = pd.DataFrame(resultats)
    resultats.insert(0, 'Moyenne', resultats.mean(axis=1))
    return resultats.sort_values('Moyenne', ascending=False)


def graphe_test(resultats, part_signalee):
    """Barres : la part des anomalies fabriquées retrouvée par chaque modèle. Le trait fin va du moins bon essai au meilleur."""
    essais = resultats.drop(columns='Moyenne')
    # Du meilleur (en haut) au moins bon (en bas)
    ordre = resultats.index[::-1]
    # Le chiffre est écrit à côté du nom du modèle : dans la barre, il serait caché par le trait noir quand la barre est courte
    fig = go.Figure(go.Bar(
        x=resultats.loc[ordre, 'Moyenne'], y=[f"{nom} : {fr(resultats.loc[nom, 'Moyenne'], 0)} %" for nom in ordre], orientation='h',
        marker_color=[COULEURS[FAMILLES.get(nom, PROFIL)] for nom in ordre], showlegend=False,
        error_x=dict(type='data', symmetric=False, color='black', thickness=1.5,
                     array=(essais.max(axis=1) - resultats['Moyenne']).loc[ordre],
                     arrayminus=(resultats['Moyenne'] - essais.min(axis=1)).loc[ordre]),
        hovertemplate='%{y}<br>%{x:.1f} % retrouvées en moyenne<extra></extra>'))
    for famille in [f for f in COULEURS if f in {FAMILLES.get(nom, PROFIL) for nom in ordre}]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(color=COULEURS[famille], size=14, symbol='square'),
                                 name=famille))
    fig.add_vline(x=part_signalee * 100, line=dict(color='gray', dash='dash', width=2),
                  annotation_text=f'Au hasard : {fr(part_signalee * 100, 0)} %', annotation_position='top')
    fig.update_xaxes(title_text='Part des anomalies fabriquées retrouvées (en %)', range=[0, 100])
    fig.update_yaxes(ticksuffix='  ')
    fig.update_layout(title='Le test : quel modèle retrouve les salaires qu\'on a baissés ?')
    montrer(fig, hauteur=650)


def constat_test(resultats, part_signalee):
    """Le modèle qui retrouve le plus d'anomalies fabriquées, ceux qu'on ne peut pas départager de lui, et le moins bon."""
    essais = resultats.drop(columns='Moyenne')
    meilleur, pire = resultats['Moyenne'].idxmax(), resultats['Moyenne'].idxmin()
    hasard = part_signalee * 100
    phrases = [f"« {meilleur} » retrouve en moyenne {fr(resultats.loc[meilleur, 'Moyenne'], 0)} % des salaires baissés "
               f"(de {fr(essais.loc[meilleur].min(), 0)} % à {fr(essais.loc[meilleur].max(), 0)} % selon l'essai). "
               f"Un tirage au hasard en retrouverait {fr(hasard, 0)} %."]
    # Deux modèles ne se départagent pas si le meilleur essai de l'un atteint le moins bon essai du premier
    proches = [nom for nom in resultats.index if nom != meilleur and essais.loc[nom].max() >= essais.loc[meilleur].min()]
    phrases.append(("On ne peut pas le départager de : " + ', '.join(f'« {n} »' for n in proches) + " (leurs essais se croisent).") if proches
                   else "Aucun autre modèle ne l'atteint, même sur son meilleur essai : l'écart est réel.")
    if pire != meilleur:
        phrases.append(f"Le moins bon : « {pire} » ({fr(resultats.loc[pire, 'Moyenne'], 0)} %).")
    au_hasard = [nom for nom in resultats.index if resultats.loc[nom, 'Moyenne'] <= 2 * hasard]
    if au_hasard:
        phrases.append("Proches du hasard (moins de deux fois mieux) : " + ', '.join(f'« {n} »' for n in au_hasard) + '.')
    constat(*phrases)


# ---------------------------------------------------------------------------------------------------
# Étape 6 : les salariés signalés par le plus de modèles
# ---------------------------------------------------------------------------------------------------

def plus_signales(base, signes, combien=20):
    """Les salariés signalés par le plus de modèles, avec le nom de ces modèles."""
    vue = base[[c for c in ['Matricule', 'Job_Family', 'Niveau', 'Fixe_Annuel_MAD', 'Min', 'Mid', 'Max', 'Compa_Ratio', 'Age', 'Anciennete']
                if c in base.columns]].copy()
    vue['Nombre de modèles'] = signes.sum(axis=1)
    vue['Modèles'] = signes.apply(lambda ligne: ', '.join(ligne.index[ligne]), axis=1)
    # À nombre de modèles égal, le Compa-Ratio le plus bas d'abord
    vue = vue[vue['Nombre de modèles'] > 0].sort_values(['Nombre de modèles', 'Compa_Ratio'], ascending=[False, True])
    display(vue.head(combien))
    constat(f"{len(vue)} salariés sont signalés par au moins un modèle ; le tableau montre les {min(combien, len(vue))} premiers.",
            f"Le plus signalé l'est par {int(vue['Nombre de modèles'].max())} modèles sur {signes.shape[1]}." if len(vue) else "")
