#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ANALYSE 1 : LE DIPLÔME DANS LES GROUPES DE COLLÈGUES
====================================================

La question : faut-il comparer chaque salarié aux collègues du même diplôme ? Ça n'a de sens que si,
à niveau et métier égaux, le diplôme fait varier le salaire.

Ce que fait ce fichier, sans rien changer à la détection :
1. Il trace le CompaRatio (salaire divisé par le milieu de la grille du niveau + métier) de chaque
   tranche de diplôme. Comme chacun est comparé à sa propre grille, tous les niveaux et tous les métiers
   vont sur le même graphique. Puis la même chose, tranche d'ancienneté par tranche d'ancienneté.
2. Il forme les groupes de collègues deux fois : comme d'habitude, puis avec une étape plus précise en
   tête, qui ajoute la tranche de diplôme. Il compare leur taille et l'étalement des salaires dans un
   groupe : si le diplôme compte, les collègues de même diplôme se ressemblent plus.
3. Il lance la détection avec les deux façons de former les groupes et montre les priorités et les
   alertes « écart aux collègues » qui changent.

Utilisation, depuis le dossier du projet (ou double-clic sur analyse_diplomes/lancer_analyses.bat) :
      python analyse_diplomes/cohortes.py
Résultats dans output/analyse_diplomes/ : la page cohortes_AAAA-MM-JJ_HH-MM-SS.html, et
cohortes.xlsx, la liste des salariés dont la priorité ou l'alerte « écart aux collègues » change.
"""

from commun import (INCONNU, PROJET, TRANCHES, charger, detection, ecrire_page, mouvement, pour_cent, salaries,
                    tableau_priorites, virgule)
from anomaly_cohortes import NOMS_LISIBLES, former_cohortes

# Les couleurs des tranches : du plus clair (moins diplômé) au plus foncé, dans l'or de la charte Repères.
# Le gris est pour les diplômes inconnus.
COULEURS = {"BAC+2 ou moins": "#f2cf7e", "BAC+3 ou BAC+4": "#e9a21b", "BAC+5 et plus": "#9a5d0c",
            INCONNU: "#c9ced4"}
ANCIENNETES = ["0-2", "3-5", "6-12", "13-20", ">20"]


def ecart_collegues(df):
    """Vrai pour les salariés qui ont l'alerte « écart aux collègues » (PEER_OUTLIER)."""
    return df["Rule_Flags"].fillna("").str.contains("PEER_OUTLIER")


def bilan_groupes(df, etapes, taille_min):
    """Ce que donnent les groupes de collègues formés avec ces étapes :
    - precis : part des salariés comparés au groupe le plus précis (la première étape) ;
    - taille : la taille du groupe d'un salarié, la médiane (la moitié des salariés sont dans un groupe
      plus petit) ;
    - petits : part des salariés dans un groupe tout juste assez grand (moins de deux fois la taille
      minimale) ;
    - etalement : l'écart entre le salaire du quart bas et celui du quart haut du groupe, en % du salaire
      du milieu ; la médiane sur tous les salariés. Si un critère explique les salaires, les collègues se
      ressemblent plus et cet étalement baisse."""
    c = former_cohortes(df, {"cohort_min_size": taille_min, "cohort_widening_steps": etapes})
    # Le nombre de critères du groupe reçu = le nombre de « | » dans son nom, plus 1.
    criteres = c["Cohort_Key"].str.count(r"\|") + 1
    return {"precis": (criteres == len(etapes[0].split("|"))).mean(),
            "taille": c["Cohort_Size"].median(),
            "petits": (c["Cohort_Size"] < 2 * taille_min).mean(),
            "etalement": ((c["Cohort_P75"] - c["Cohort_P25"]) / c["Cohort_Median"]).median()}


def boite(valeurs, nom, couleur, x=None):
    """Une boîte à moustaches. Les points isolés ne sont pas dessinés : avec des milliers de salariés, ils
    cacheraient les boîtes."""
    trace = {"type": "box", "y": [round(v, 3) for v in valeurs], "name": nom, "fillcolor": couleur,
             "marker": {"color": couleur}, "line": {"color": "#4a2c1d", "width": 1.5}, "boxpoints": False,
             "hovertemplate": "%{y:.2f}<extra>" + nom + "</extra>"}
    if x is not None:
        trace.update({"x": x, "legendgroup": nom, "offsetgroup": nom, "alignmentgroup": "a"})
    return trace


if __name__ == "__main__":
    rule_params, df = charger()
    taille_min = int(rule_params.get("cohort_min_size", 15))
    # Les groupes sans le diplôme : ceux du fichier de règles. Avec : les mêmes, précédés d'une étape plus
    # précise qui ajoute la tranche de diplôme à la première.
    etapes_sans = [e for e in rule_params["cohort_widening_steps"] if "Tranche_Etude" not in e]
    etapes_avec = [etapes_sans[0] + "|Tranche_Etude"] + etapes_sans

    print("Détection avec les groupes habituels...")
    avant = detection(df, dict(rule_params, cohort_widening_steps=etapes_sans))
    print("Détection avec le diplôme dans les groupes...")
    apres = detection(df, dict(rule_params, cohort_widening_steps=etapes_avec))

    # 1. Le CompaRatio de chaque tranche de diplôme.
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

    # 2. Le même graphe, tranche d'ancienneté par tranche d'ancienneté.
    anciennetes = [a for a in ANCIENNETES if (cr["Anciennete_Bucket"] == a).any()]
    graphe2 = [boite(sous["CompaRatio"], t, COULEURS[t], x=sous["Anciennete_Bucket"].tolist())
               for t in TRANCHES
               if len(sous := cr[(cr["Tranche"] == t) & cr["Anciennete_Bucket"].isin(anciennetes)])]

    # 3. Les groupes de collègues, sans et avec le diplôme.
    g_sans, g_avec = bilan_groupes(df, etapes_sans, taille_min), bilan_groupes(df, etapes_avec, taille_min)
    lignes = "".join(f"<tr><th>{nom}</th><td>{pour_cent(g['precis'])}</td><td>{virgule(g['taille'], 0)}</td>"
                     f"<td>{pour_cent(g['petits'])}</td><td>{pour_cent(g['etalement'], 1)}</td></tr>"
                     for nom, g in [("Sans le diplôme", g_sans), ("Avec le diplôme", g_avec)])
    baisse = g_sans["etalement"] - g_avec["etalement"]
    constat3 = (f"Avec le diplôme, l'étalement passe de {pour_cent(g_sans['etalement'], 1)} "
                f"à {pour_cent(g_avec['etalement'], 1)}"
                + (f" ({pour_cent(baisse, 1)} de moins)" if round(baisse * 100, 1) > 0 else
                   " : il ne baisse pas" if round(baisse * 100, 1) == 0 else f" ({pour_cent(-baisse, 1)} de plus)")
                + f", et la taille médiane d'un groupe de {virgule(g_sans['taille'], 0)} à "
                f"{virgule(g_avec['taille'], 0)} personnes.")

    # 4. et 5. Les priorités et l'alerte « écart aux collègues ».
    a_traiter_avant, a_traiter_apres = avant["Severity"] != "Info", apres["Severity"] != "Info"
    entrent, sortent = apres[a_traiter_apres & ~a_traiter_avant], avant[a_traiter_avant & ~a_traiter_apres]
    # Quand aucune priorité ne bouge, on le dit en une phrase plutôt que « aucun salarié... aucun salarié ».
    constat4 = ("Aucune priorité ne change." if (avant["Severity"] == apres["Severity"]).all()
                else mouvement(entrent, sortent, ("Deviennent à traiter", "ne le sont plus")))
    alerte_avant, alerte_apres = ecart_collegues(avant), ecart_collegues(apres)
    nouvelles, disparues = apres[alerte_apres & ~alerte_avant], avant[alerte_avant & ~alerte_apres]
    constat5 = (f"Alertes : {salaries(alerte_avant.sum())} avec les groupes habituels, {salaries(alerte_apres.sum())} "
                "avec le diplôme. " + mouvement(nouvelles, disparues, ("Nouvelles alertes", "disparues")))
    # Les points de cette alerte, lus dans le fichier de règles : la phrase reste juste si le comité les change.
    points = rule_params["severity_weights"]["peer_outlier"]
    poids = (f"Elle ne donne des points ({virgule(points, 0)} sur 100) qu'aux salariés très en dessous de leurs "
             "collègues ; un peu en dessous, c'est une simple étiquette. Elle peut donc changer sans que la priorité "
             "bouge.")
    # Le groupe ajouté, écrit en clair (« niveau + métier + ... ») plutôt qu'avec les noms des colonnes.
    groupe_txt = " + ".join(NOMS_LISIBLES.get(c, c) for c in etapes_avec[0].split("|"))

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
    corps = f"""
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
<div id="g2" class="graphe"></div>

<h2>3. Les groupes de collègues, sans et avec le diplôme</h2>
<p class="lire">Avec le diplôme, chaque salarié est d'abord comparé au groupe {groupe_txt}. Si ce groupe compte
moins de {taille_min} personnes, ou si son diplôme est inconnu, il retrouve les groupes habituels. L'étalement est
l'écart entre le salaire du quart bas et celui du quart haut du groupe, en % du salaire du milieu. S'il baisse
nettement sans que les groupes deviennent trop petits, le diplôme rend la comparaison plus juste.</p>
<table><tr><th></th><th>Comparés au groupe le plus précis</th><th>Taille médiane du groupe</th>
<th>Dans un groupe de moins de {2 * taille_min} personnes</th><th>Étalement des salaires dans le groupe</th></tr>{lignes}</table>
<p class="constat">{constat3}</p>

<h2>4. Les priorités, sans et avec le diplôme</h2>
<p class="lire">Chaque case compte les salariés qui ont la priorité de la ligne avec les groupes habituels, et celle
de la colonne avec le diplôme. La diagonale, en gris, regroupe ceux qui ne changent pas.</p>
{tableau_priorites(avant, apres)}
<p class="constat">{constat4}</p>

<h2>5. L'alerte « écart aux collègues », sans et avec le diplôme</h2>
<p class="lire">C'est la seule règle qui utilise le groupe de collègues, donc la seule que le diplôme change. {poids}</p>
<p class="constat">{constat5}</p>"""
    page = ecrire_page("cohortes", "Le diplôme dans les groupes de collègues", df, corps, graphes)

    # Les salariés dont la priorité ou l'alerte « écart aux collègues » change, avec ce qui permet de juger.
    change = (avant["Severity"] != apres["Severity"]) | (alerte_avant != alerte_apres)
    oui_non = {True: "oui", False: "non"}
    liste = df.loc[change, ["Matricule", "Entite_N1", "Job_Family", "Niveau", "Anciennete_Bucket",
                            "Niveau_Etude_Max", "Tranche_Etude", "Fixe_Annuel_MAD", "CompaRatio"]].assign(
        Priorite_groupes_habituels=avant.loc[change, "Severity"],
        Priorite_avec_diplome=apres.loc[change, "Severity"],
        Ecart_collegues_groupes_habituels=alerte_avant[change].map(oui_non),
        Ecart_collegues_avec_diplome=alerte_apres[change].map(oui_non),
        Groupe_habituel=avant.loc[change, "Criteres_Cohorte"], Groupe_avec_diplome=apres.loc[change, "Criteres_Cohorte"],
        PeerZ_groupe_habituel=avant.loc[change, "PeerZ"].round(2), PeerZ_avec_diplome=apres.loc[change, "PeerZ"].round(2))
    excel = PROJET / "output" / "analyse_diplomes" / "cohortes.xlsx"
    liste.to_excel(excel, index=False)
    print(f"Page : {page}")
    print(f"Salariés dont la priorité ou l'alerte « écart aux collègues » change ({change.sum()}) : {excel}")
