#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
FAUT-IL UTILISER LE DIPLÔME DANS LA DÉTECTION ?
===============================================

Une seule page, qui regarde le diplôme de trois façons, du plus simple au plus compliqué, sans rien
changer à la détection :

1. et 2. La position dans la grille (le CompaRatio : salaire divisé par le milieu de la grille du
   niveau + métier) de chaque tranche de diplôme, en tout puis tranche d'ancienneté par tranche
   d'ancienneté. Comme chacun est comparé à sa propre grille, tous les niveaux et tous les métiers vont
   sur le même graphique.
3. et 4. La régression qui prédit un salaire (src/anomaly_signal_regression.py, le repère de l'aide à la
   décision) : se trompe-t-elle moins si elle connaît le diplôme, et de combien le diplôme change-t-il
   le salaire qu'elle prédit ?
   - Elle est essayée 50 fois : on coupe les salariés en 5 paquets, le modèle apprend sur 4 et on regarde
     de combien il se trompe sur le 5e, qu'il n'a pas vu ; on recommence en changeant de paquet, puis on
     refait tout 10 fois avec d'autres paquets. Pourquoi tant d'essais : avec un seul tirage, une petite
     amélioration peut venir du hasard.
   - Quatre modèles : sans le diplôme ; avec la tranche de diplôme ; avec la tranche et la catégorie ; et
     un témoin, avec la tranche et la catégorie MÉLANGÉES AU HASARD entre salariés du même métier et du
     même niveau. Le témoin dit combien on gagne rien qu'en ajoutant des colonnes qui ne veulent rien
     dire : le diplôme n'aide vraiment que s'il fait nettement mieux que lui.
5. L'IA (Isolation Forest) : quand elle regarde aussi le diplôme, remonte-t-elle certaines tranches de
   diplôme parmi les salariés les plus atypiques ? L'IA repère ce qui est RARE, pas forcément ce qui est
   mal payé : un diplôme rare peut suffire à faire remonter quelqu'un.

Utilisation, depuis le dossier du projet (ou double-clic sur analyse_diplomes/lancer_analyses.bat) :
      python analyse_diplomes/diplome.py
Résultat dans output/analyse_diplomes/ : la page diplome_AAAA-MM-JJ_HH-MM-SS.html.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import RepeatedKFold

from commun import INCONNU, TRANCHES, charger, detection, ecrire_page, pour_cent, virgule
from anomaly_signal_regression import COLONNES, tableau_x
from anomaly_signal_iforest import FEATS
from anomaly_signal_fort import CATEGORIE

AVEC_TRANCHE = COLONNES + ["Tranche_Etude"]
AVEC_TOUT = COLONNES + ["Tranche_Etude", "Cat_Ecole_Max"]
# Les couleurs des tranches : du plus clair (moins diplômé) au plus foncé, dans l'or de la charte Repères.
# Le gris est pour les diplômes inconnus.
COULEURS = {"BAC+2 ou moins": "#f2cf7e", "BAC+3 ou BAC+4": "#e9a21b", "BAC+5 et plus": "#9a5d0c",
            INCONNU: "#c9ced4"}
ANCIENNETES = ["0-2", "3-5", "6-12", "13-20", ">20"]


# -----------------------------------------------------------------------------
# 1. et 2. La position dans la grille
# -----------------------------------------------------------------------------

def boite(valeurs, nom, couleur, x=None):
    """Une boîte à moustaches. Les points isolés ne sont pas dessinés : avec des milliers de salariés, ils
    cacheraient les boîtes."""
    trace = {"type": "box", "y": [round(v, 3) for v in valeurs], "name": nom, "fillcolor": couleur,
             "marker": {"color": couleur}, "line": {"color": "#4a2c1d", "width": 1.5}, "boxpoints": False,
             "hovertemplate": "%{y:.2f}<extra>" + nom + "</extra>"}
    if x is not None:
        trace.update({"x": x, "legendgroup": nom, "offsetgroup": nom, "alignmentgroup": "a"})
    return trace


def partie_grille(df):
    """Le CompaRatio de chaque tranche de diplôme, en tout (partie 1) puis par ancienneté (partie 2) : le
    HTML des deux parties et leurs graphes."""
    cr = df[df["CompaRatio"].notna()].assign(Tranche=lambda d: d["Tranche_Etude"].fillna(INCONNU))
    presentes = [t for t in TRANCHES + [INCONNU] if (cr["Tranche"] == t).any()]
    graphe1 = [boite(cr.loc[cr["Tranche"] == t, "CompaRatio"], f"{t} ({virgule((cr['Tranche'] == t).sum(), 0)})",
                     COULEURS[t]) for t in presentes]
    connus = cr[cr["Tranche"] != INCONNU].groupby("Tranche")["CompaRatio"]
    medianes = connus.median().reindex(TRANCHES).dropna()
    if len(medianes) >= 2:
        ecart = medianes.max() - medianes.min()
        # La hauteur moyenne d'une boîte, pour juger l'écart : un écart bien plus petit qu'une boîte veut
        # dire que les boîtes se recouvrent presque entièrement.
        hauteur = connus.quantile(0.75).sub(connus.quantile(0.25)).mean()
        constat1 = ("CompaRatio médian : " + " ; ".join(f"{t} : {virgule(m)}" for t, m in medianes.items())
                    + f". Entre la tranche la mieux placée et la moins bien placée, l'écart est de "
                    f"{virgule(ecart * 100, 1)} % du milieu de la grille, pour des boîtes hautes de "
                    f"{virgule(hauteur * 100, 0)} % en moyenne.")
    else:
        constat1 = "Une seule tranche de diplôme est connue : il n'y a rien à comparer."

    anciennetes = [a for a in ANCIENNETES if (cr["Anciennete_Bucket"] == a).any()]
    graphe2 = [boite(sous["CompaRatio"], t, COULEURS[t], x=sous["Anciennete_Bucket"].tolist())
               for t in TRANCHES
               if len(sous := cr[(cr["Tranche"] == t) & cr["Anciennete_Bucket"].isin(anciennetes)])]

    axe_cr = {"title": {"text": "CompaRatio (salaire ÷ milieu de la grille)"}, "tickformat": ".2f",
              "gridcolor": "#e6e8eb", "zeroline": False}
    ligne_1 = [{"type": "line", "xref": "paper", "x0": 0, "x1": 1, "y0": 1, "y1": 1,
                "line": {"color": "#5b6b7d", "dash": "dash", "width": 1}}]
    marges = {"l": 70, "r": 20, "t": 20, "b": 60}
    graphes = {
        "g1": (graphe1, {"showlegend": False, "yaxis": axe_cr, "shapes": ligne_1, "margin": marges}),
        "g2": (graphe2, {"boxmode": "group", "yaxis": axe_cr, "shapes": ligne_1, "margin": marges,
                         "legend": {"orientation": "h", "y": 1.08},
                         "xaxis": {"title": {"text": "Tranche d'ancienneté (années)"},
                                   "categoryorder": "array", "categoryarray": anciennetes}}),
    }
    html = f"""
<h2>1. La position dans la grille selon le diplôme</h2>
<p class="lire">Chaque boîte regroupe la moitié des salariés d'une tranche de diplôme (leur nombre est entre
parenthèses), et le trait du milieu est la médiane. Chacun est comparé à la grille de son niveau et de son métier, ce
qui permet de mettre tout le monde sur le même graphique. <b>Boîtes à la même hauteur</b> : à niveau et métier égaux,
le diplôme ne change pas le salaire. <b>Boîtes en escalier</b> : il le change.</p>
<div id="g1" class="graphe"></div>
<p class="constat">{constat1}</p>

<h2>2. Même chose, selon l'ancienneté</h2>
<p class="lire">Un escalier chez les plus récents qui disparaît avec les années veut dire que le diplôme ne joue qu'à
l'embauche. Un escalier à toutes les anciennetés veut dire qu'il joue toute la carrière.</p>
<div id="g2" class="graphe"></div>"""
    return html, graphes


# -----------------------------------------------------------------------------
# 3. et 4. La régression
# -----------------------------------------------------------------------------

def essais(df, colonnes):
    """Les 50 essais d'un modèle. Pour chacun : l'erreur moyenne en kMAD, la part du salaire expliquée
    (de 0 à 1) et la largeur de la fourchette qui contient le vrai salaire 9 fois sur 10, en % du salaire
    prédit. Les paquets sont les mêmes pour tous les modèles (random_state=42) : on les compare sur les
    mêmes salariés mis de côté."""
    X = tableau_x(df, colonnes)
    Y = np.log(df["Fixe_Annuel_MAD"]).to_numpy()
    lignes = []
    for apprend, verifie in RepeatedKFold(n_splits=5, n_repeats=10, random_state=42).split(X):
        predit = LinearRegression().fit(X.iloc[apprend], Y[apprend]).predict(X.iloc[verifie])
        erreur = Y[verifie] - predit
        bas, haut = np.quantile(erreur, [0.05, 0.95])
        lignes.append({"mae": np.mean(np.abs(np.exp(Y[verifie]) - np.exp(predit))),
                       "r2": 1 - np.sum(erreur ** 2) / np.sum((Y[verifie] - Y[verifie].mean()) ** 2),
                       "largeur": (np.exp(haut) - np.exp(bas)) * 100})
    return pd.DataFrame(lignes)


def melanger(df):
    """Le témoin : la tranche et la catégorie de diplôme mélangées au hasard entre salariés du même métier
    et du même niveau. Le diplôme garde la même répartition dans chaque métier + niveau, mais n'a plus
    aucun lien avec le salaire de la personne."""
    hasard = np.random.default_rng(42)
    df = df.copy()
    colonnes = ["Tranche_Etude", "Cat_Ecole_Max"]
    for lignes in df.groupby(["Job_Family", "Niveau"]).groups.values():
        df.loc[lignes, colonnes] = df.loc[lignes, colonnes].to_numpy()[hasard.permutation(len(lignes))]
    return df


def salaires_predits(df, colonne):
    """Pour chaque valeur de la colonne (chaque tranche, ou chaque catégorie de diplôme) : le salaire que
    le modèle prédit quand on donne cette valeur à TOUS les salariés, sans rien changer d'autre. Rend,
    pour chaque valeur, le salaire du milieu (la médiane) de ces salaires prédits, en kMAD (milliers de
    MAD), comme dans les fichiers d'entrée.
    Pourquoi donner la valeur à tout le monde : chaque barre est alors calculée sur les mêmes salariés,
    avec les mêmes métiers, niveaux, anciennetés, etc. Seul le diplôme change d'une barre à l'autre :
    toute la différence entre deux barres vient donc de lui.
    Pourquoi la médiane et pas la moyenne : quelques très gros salaires tireraient la moyenne vers le
    haut, et elle ne ressemblerait plus au salaire d'un salarié ordinaire.
    Les valeurs viennent des colonnes du diplôme du fichier des salariés, pas d'une liste écrite à l'avance : si les catégories
    sont écrites autrement, elles apparaissent quand même."""
    valeurs = list(df[colonne].value_counts().index)
    if colonne == "Tranche_Etude":
        # Les tranches dans leur ordre, du moins au plus diplômé, plutôt que de la plus à la moins fréquente.
        valeurs = [t for t in TRANCHES if t in valeurs]
    X = tableau_x(df, AVEC_TOUT)
    modele = LinearRegression().fit(X, np.log(df["Fixe_Annuel_MAD"]))

    def predit(valeur):
        x = tableau_x(df.assign(**{colonne: valeur}), AVEC_TOUT).reindex(columns=X.columns, fill_value=0)
        # Le modèle apprend les salaires sous une forme qui compte les écarts en % plutôt qu'en kMAD (np.log,
        # voir essais) : np.exp les remet en kMAD.
        return np.exp(modele.predict(x))

    return pd.Series({v: float(np.median(predit(v))) for v in valeurs}, dtype=float)


def kmad(x):
    """206.43 -> « 206,4 kMAD » (206 400 MAD)."""
    return f"{virgule(x, 1)} kMAD"


def partie_regression(df):
    """Le tableau des erreurs (partie 3) et les graphes de l'effet du diplôme (partie 4) : le HTML des
    deux parties et leurs graphes."""
    # Un salarié sans salaire utilisable ne peut pas servir à apprendre un salaire.
    df = df[df["Fixe_Annuel_MAD"] > 0].reset_index(drop=True)

    print("Régression : essais des quatre modèles (50 essais chacun)...")
    resultats = {"Sans le diplôme": essais(df, COLONNES),
                 "Avec la tranche de diplôme": essais(df, AVEC_TRANCHE),
                 "Avec la tranche et la catégorie": essais(df, AVEC_TOUT),
                 "Témoin : diplômes mélangés au hasard": essais(melanger(df), AVEC_TOUT)}

    lignes = "".join(f"<tr><th>{nom}</th><td>{virgule(r['mae'].mean(), 1)}</td>"
                     f"<td>{virgule(r['r2'].mean(), 2)}</td><td>± {virgule(r['largeur'].mean() / 2, 0)} %</td></tr>"
                     for nom, r in resultats.items())
    sans, avec, temoin = (resultats[n] for n in ["Sans le diplôme", "Avec la tranche et la catégorie",
                                                 "Témoin : diplômes mélangés au hasard"])
    gain, gain_temoin = sans["mae"].mean() - avec["mae"].mean(), sans["mae"].mean() - temoin["mae"].mean()
    mieux = (avec["mae"] < sans["mae"]).mean()
    # Le verdict suit les chiffres : le diplôme n'aide que s'il gagne plus que le témoin ET fait mieux que le
    # modèle sans lui dans au moins 9 essais sur 10 (sinon, son gain peut venir du hasard des paquets).
    if gain > max(gain_temoin, 0) and mieux >= 0.9:
        verdict = (f"Le diplôme rend le salaire prédit plus juste : il fait mieux que le modèle sans lui dans "
                   f"{virgule(mieux * 100, 0)} % des essais, et mieux que des diplômes tirés au hasard.")
    elif gain <= max(gain_temoin, 0):
        verdict = "Le diplôme ne rend pas le salaire prédit plus juste : il ne fait pas mieux que des diplômes tirés au hasard."
    else:
        verdict = (f"Le diplôme ne rend pas le salaire prédit nettement plus juste : il ne fait mieux que dans "
                   f"{virgule(mieux * 100, 0)} % des essais.")
    constat3 = (f"Erreur moyenne : {virgule(sans['mae'].mean(), 1)} kMAD sans le diplôme, "
                f"{virgule(avec['mae'].mean(), 1)} kMAD avec, {virgule(temoin['mae'].mean(), 1)} kMAD avec le témoin. "
                f"{verdict}")

    print("Régression : salaire prédit pour chaque diplôme...")
    graphes, phrases, blocs = {}, [], []
    for cle, colonne, nom, couleur in [("r_t", "Tranche_Etude", "la tranche de diplôme", "#e9a21b"),
                                       ("r_c", "Cat_Ecole_Max", "la catégorie de diplôme", "#5b6b7d")]:
        salaires = salaires_predits(df, colonne)
        if len(salaires) < 2:
            connu = "aucune valeur n'est connue" if salaires.empty else f"une seule valeur est connue ({salaires.index[0]})"
            phrases.append(f"Pour {nom}, {connu} : rien à comparer.")
            continue
        # Les salaires sont déjà écrits au bout des barres : la phrase ne donne que l'écart entre le plus
        # bas et le plus haut, en kMAD par an et en %.
        bas, haut = salaires.idxmin(), salaires.idxmax()
        ecart = salaires[haut] - salaires[bas]
        phrases.append(f"Pour {nom}, le salaire prédit va de {kmad(salaires[bas])} (« {bas} ») à {kmad(salaires[haut])} "
                       f"(« {haut} ») : {kmad(ecart)} d'écart par an, soit {pour_cent(ecart / salaires[bas], 1)}.")
        # Pourquoi l'axe part de 0 : un axe qui commencerait plus haut grossirait les petites différences, et
        # deux salaires presque égaux auraient l'air très différents. Le 1,25 laisse la place d'écrire le
        # salaire au bout de la barre la plus longue.
        graphes[cle] = ([{"type": "bar", "orientation": "h", "y": [str(v) for v in salaires.index],
                          "x": salaires.round(1).tolist(), "marker": {"color": couleur},
                          "text": [kmad(s) for s in salaires], "textposition": "outside",
                          "hovertemplate": "%{x:,.1f} kMAD<extra></extra>"}],
                        {"showlegend": False, "margin": {"l": 200, "r": 40, "t": 40, "b": 50},
                         "title": {"text": f"Salaire prédit selon {nom}", "font": {"size": 14}, "x": 0},
                         "xaxis": {"title": {"text": "Salaire annuel prédit, salarié du milieu (kMAD)"},
                                   "gridcolor": "#e6e8eb", "tickformat": ",.0f",
                                   "range": [0, float(salaires.max()) * 1.25]},
                         "yaxis": {"autorange": "reversed"}})
        blocs.append(f'<div id="{cle}" class="graphe" style="height: 300px"></div>')

    html = f"""
<h2>3. Les erreurs du modèle, sans et avec le diplôme</h2>
<p class="lire">Le modèle est la régression qui devine le salaire d'un salarié à partir de son métier, son niveau,
son ancienneté, son âge, ses notes et le Hot job. Chaque modèle est essayé 50 fois : il apprend sur 80 % des
salariés, puis on mesure son erreur sur les 20 % qu'il n'a pas vus. Le <b>témoin</b> a des diplômes mélangés au
hasard : il montre ce qu'on gagne avec des colonnes qui ne veulent rien dire. Le diplôme n'aide que s'il fait
nettement mieux que lui.</p>
<table><tr><th>Modèle</th><th>Erreur moyenne (kMAD)</th><th>Part du salaire expliquée (0 = rien, 1 = tout)</th>
<th>Marge d'erreur (9 fois sur 10)</th></tr>{lignes}</table>
<p class="constat">{constat3}</p>

<h2>4. De combien le diplôme change le salaire prédit</h2>
<p class="lire">Pour chaque diplôme, on fait comme si tous les salariés l'avaient, sans rien changer d'autre (métier,
niveau, ancienneté, âge, notes, Hot job), et on demande au modèle leur salaire. Chaque barre donne le salaire du
milieu : la moitié des salariés auraient moins, l'autre moitié plus. <b>Des barres de même longueur</b> voudraient
dire que le diplôme ne change pas le salaire prédit ; plus elles sont différentes, plus le diplôme pèse.</p>
{"".join(blocs)}
<p class="constat">{" ".join(phrases)}</p>"""
    return html, graphes


# -----------------------------------------------------------------------------
# 5. L'IA
# -----------------------------------------------------------------------------

def encoder_categories(df: pd.DataFrame):
    """Ajoute une colonne 0/1 par catégorie de diplôme présente dans le fichier, nommée « Categorie : »
    suivi de la catégorie (c'est ce nom que l'explication de l'IA sait écrire en clair). Rend le tableau
    et la liste des colonnes ajoutées.
    Pourquoi des colonnes 0/1 : une catégorie n'a pas d'ordre (un diplôme de commerce n'est pas « plus »
    qu'un diplôme d'ingénieur), on ne peut donc pas la numéroter. Pourquoi les catégories du fichier et
    pas une liste fixe : si elles sont écrites autrement, une liste fixe ne les reconnaîtrait pas.
    Une catégorie inconnue laisse les cases vides, pas à 0 : « 0 » voudrait dire « on sait qu'il n'a pas
    ce diplôme »."""
    categorie = df["Cat_Ecole_Max"].astype("string").str.strip().str.upper()
    colonnes = []
    for valeur in sorted(categorie.dropna().unique()):
        colonne = CATEGORIE + valeur
        df = df.assign(**{colonne: (categorie == valeur).astype(float).where(categorie.notna())})
        colonnes.append(colonne)
    return df, colonnes


def partie_ia(df, rule_params):
    """Pour chaque tranche de diplôme, la part des salariés qui sont parmi les plus atypiques pour l'IA,
    sans puis avec le diplôme (partie 5) : le HTML de la partie et son graphe."""
    df, categories = encoder_categories(df)
    print("IA : détection avec l'IA habituelle...")
    avant = detection(df, rule_params)
    print("IA : détection avec le diplôme dans l'IA...")
    apres = detection(df, rule_params, feats=FEATS + ["Rang_Etude_Max"] + categories)

    # « Les plus atypiques » : la même part que le signal fort (5 % avec ml_strong_signal_percentile = 0.95),
    # avant qu'il ne retire ceux qui le sont surtout parce qu'ils sont bien payés.
    part = 1 - float(rule_params["ml_strong_signal_percentile"])

    def plus_atypiques(resultat):
        return resultat["ML_AnomalyScore"] >= resultat["ML_AnomalyScore"].quantile(1 - part)

    tranche = df["Tranche_Etude"].fillna(INCONNU)
    ordre = [t for t in TRANCHES + [INCONNU] if (tranche == t).any()]
    # Pour chaque tranche : sur tous ses salariés, la part qui est parmi les plus atypiques.
    taux = pd.DataFrame({"IA habituelle": plus_atypiques(avant).groupby(tranche).mean(),
                         "IA avec le diplôme": plus_atypiques(apres).groupby(tranche).mean()}).reindex(ordre).fillna(0)

    def sur_100(v):
        return f"{virgule(v * 100, 0)} sur 100"

    graphe5 = [{"type": "bar", "orientation": "h", "name": nom, "y": ordre, "x": (taux[nom] * 100).round(1).tolist(),
                "marker": {"color": couleur}, "text": [sur_100(v) for v in taux[nom]], "textposition": "outside",
                "hovertemplate": "%{x:.1f} sur 100<extra>" + nom + "</extra>"}
               for nom, couleur in [("IA habituelle", "#c9ced4"), ("IA avec le diplôme", "#e9a21b")]]
    # La part de tous les salariés, en pointillé : ce que vaudrait chaque barre si l'IA ne regardait pas
    # du tout le diplôme ni rien qui lui est lié.
    ligne_part = [{"type": "line", "yref": "paper", "y0": 0, "y1": 1, "x0": part * 100, "x1": part * 100,
                   "line": {"color": "#5b6b7d", "dash": "dash", "width": 1}}]

    # Les tranches que le diplôme fait nettement plus remonter : au moins une fois et demie plus souvent
    # parmi les plus atypiques qu'avec l'IA habituelle.
    rapport = (taux["IA avec le diplôme"] / taux["IA habituelle"]).replace(np.inf, np.nan)
    trop = rapport[rapport >= 1.5].dropna()
    constat5 = ("Avec le diplôme, aucune tranche n'est nettement plus souvent parmi les plus atypiques qu'avec l'IA "
                "habituelle." if trop.empty else
                "Avec le diplôme, " + " ; ".join(
                    f"« {t} » : {sur_100(taux.at[t, 'IA avec le diplôme'])} au lieu de "
                    f"{sur_100(taux.at[t, 'IA habituelle'])} ({virgule(r, 1)} fois plus souvent)" for t, r in trop.items())
                + ".")
    liste_categories = ", ".join(c[len(CATEGORIE):] for c in categories) or "aucune"

    html = f"""
<h2>5. Le diplôme des plus atypiques pour l'IA</h2>
<p class="lire">L'IA cherche les profils rares. Avec le diplôme, elle regarde en plus le niveau d'études et la
catégorie du diplôme ({liste_categories}). Chaque barre dit, sur 100 salariés de la tranche, combien sont parmi les
{pour_cent(part)} les plus atypiques : en gris avec l'IA habituelle, en orange avec le diplôme. Le pointillé marque
{sur_100(part)}, la part de l'ensemble des salariés. <b>Une barre orange nettement plus longue que la grise</b> voudrait
dire que l'IA remonte ces salariés à cause de leur diplôme, pas forcément de leur salaire.</p>
<div id="g5" class="graphe" style="height: 340px"></div>
<p class="constat">{constat5}</p>"""
    graphes = {"g5": (graphe5, {"barmode": "group", "shapes": ligne_part,
                                "margin": {"l": 130, "r": 80, "t": 30, "b": 50},
                                "legend": {"orientation": "h", "y": 1.12, "traceorder": "normal"},
                                "xaxis": {"title": {"text": "Salariés parmi les plus atypiques, sur 100 de la tranche"},
                                          "gridcolor": "#e6e8eb", "rangemode": "tozero"},
                                "yaxis": {"autorange": "reversed"}})}
    return html, graphes


if __name__ == "__main__":
    rule_params, df = charger()
    # Les parties vont du plus simple au plus compliqué : d'abord les vrais salaires, sans modèle (la
    # grille) ; puis la régression, qui confirme en tenant compte de tout le reste en même temps ; enfin
    # l'IA, qui ne compte que si le diplôme joue sur le salaire.
    grille_html, grille_graphes = partie_grille(df)
    regression_html, regression_graphes = partie_regression(df)
    ia_html, ia_graphes = partie_ia(df, rule_params)
    corps = f"""
<p class="lire">Cette page compare les salaires sans puis avec le diplôme, du plus simple au plus compliqué : la
position dans la grille (parties 1 et 2), la régression qui prédit un salaire (parties 3 et 4) et l'IA (partie 5).
Elle ne change rien à la détection.</p>
{grille_html}{regression_html}{ia_html}"""
    page = ecrire_page("diplome", "Faut-il utiliser le diplôme dans la détection ?", df, corps,
                       {**grille_graphes, **regression_graphes, **ia_graphes})
    print(f"Page : {page}")
