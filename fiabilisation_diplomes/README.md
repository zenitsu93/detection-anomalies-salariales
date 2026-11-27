# Fiabilisation de la base des diplômes

Ce dossier est un projet à part entière : il transforme l'extraction des diplômes du SIRH, saisie à la main, en **une ligne par salarié** avec son niveau d'études le plus élevé, le type de son diplôme, et une indication claire de la confiance qu'on peut lui accorder.

Il est né dans le projet de détection des anomalies de rémunération, qui avait besoin du niveau d'études de chaque salarié. Depuis le 27/11/2026, il a son propre dossier, sa feuille de route et son rapport.

## Le problème de départ

Dans l'extraction, chaque ligne est un diplôme d'un salarié : le nom du diplôme, son niveau, sa spécialité, l'école, la date. Telle quelle, elle ne s'utilise pas :

- les mêmes lignes reviennent plusieurs fois, surtout quand plusieurs périodes d'extraction sont fusionnées ;
- beaucoup de niveaux sont vides ;
- le même niveau s'écrit de nombreuses façons (« Bac + 5 », « BAC+5 », « Bac+5 et plus », « Niveau supérieur ») ;
- les écoles sont saisies en codes abrégés.

## Ce que fait le projet

| En entrée | En sortie |
|---|---|
| L'extraction Excel des diplômes, posée à côté du notebook | `BDD_Diplomes_FINAL.xlsx` : le fichier court, à envoyer (les données reçues et la vue par salarié) |
| `ref_ecoles.xlsx` : le référentiel des écoles | `BDD_Diplomes_FINAL_detail.xlsx` : tout le détail, pour le travail de fiabilisation |

Quatre principes ont guidé tous les choix :

1. **Ne jamais deviner.** Chaque niveau est dit sûr ou incertain. Un doute reste visible, avec son motif. Une information qui manque reste vide, et c'est signalé.
2. **Tout garder en trace.** La saisie d'origine reste à côté de la version fiabilisée, et chaque ligne garde son numéro de ligne dans l'extraction.
3. **Tout est paramétrable.** Chaque choix est écrit dans un tableau du notebook ou dans le fichier Excel des écoles : il se change sans toucher au reste.
4. **Reproductibilité.** La même démarche s'applique telle quelle à une nouvelle extraction.

## Lancer le notebook

1. Poser le fichier Excel de l'extraction dans ce dossier, à côté du notebook.
2. Double-cliquer sur `lancer_notebook.bat`. Le notebook s'ouvre dans le navigateur. Le premier lancement installe ce qu'il faut et peut prendre plusieurs minutes.
3. Dans la première cellule de code, écrire le nom du fichier dans `FICHIER_SOURCE`.
4. Menu **Run**, puis **Run All Cells**.

À savoir :

- `lancer_notebook.bat` s'appuie sur celui de la racine du projet. Si ce dossier est copié seul, il le dit au lieu de se fermer sans explication.
- Le notebook ne peut pas écrire dans un fichier ouvert : fermer les fichiers `BDD_Diplomes_FINAL` dans Excel avant de relancer.
- Sans le lanceur, il suffit de Python avec `pandas`, `numpy`, `openpyxl` et `xlsxwriter`, et d'ouvrir le notebook dans Jupyter.

## Ce que contient le dossier

| Fichier ou dossier | Ce que c'est |
|---|---|
| `Fiabilisation_Diplomes_pas_a_pas_v13.ipynb` | Le notebook de fiabilisation. Chaque étape montre sa règle, son code, puis un contrôle. |
| `lancer_notebook.bat` | Ouvre le notebook d'un double-clic. |
| `ref_ecoles.xlsx` | Le référentiel des écoles : pour chaque code du SIRH, le nom, le pays, la nature (ingénieurs, commerce, université) et le niveau de confiance. Il se complète dans Excel. |
| `Diplômes à fiabiliser - CB 19102026.xlsx`, `… 02112026.xlsx` | Deux extractions d'exemple, aux matricules fictifs. Les tableaux affichés dans le notebook viennent de celle du 02/11. |
| `documents/` | La feuille de route, le rapport et les présentations. **Ce dossier reste sur le poste** : il porte les chiffres réels, et le dépôt en ligne est public. |

Dans `documents/` :

| Dossier | Contenu |
|---|---|
| `1 - Feuille de route` | Le classeur de la feuille de route : chantiers, plan d'actions, décisions, points ouverts. |
| `2 - Rapport` | Le rapport du projet, en Word et en PDF. |
| `3 - Présentations` | Les présentations du 21/10, du 30/10 et du 23/11. |
| `scripts` | Les programmes qui construisent la feuille de route, le rapport et la restitution. |

## La démarche en neuf étapes

| Étape | Ce qu'elle fait | Où modifier |
|---|---|---|
| 0. Chargement | Lit l'extraction. Cinq colonnes servent à la fiabilisation, les autres sont gardées telles quelles. | `FICHIER_SOURCE`, `FICHIER_SORTIE`, `FICHIER_REF_ECOLES` |
| 1. Nettoyage | Met tout au même format. Les faux contenus (« - », « N/A », « Autres ») deviennent de vrais vides. | `PLACEHOLDERS` |
| 2. Niveau saisi | Ramène chaque écriture du niveau à une échelle unique. | `NIVEAUX`, `NIVEAUX_ECRITS` |
| 3. Libellé du diplôme | Donne à chaque libellé son type (master, licence, ITB…) et le niveau qu'il vaut en théorie. | `REF_DIPLOMES_MANUEL`, `REGLES_DIPLOME`, `FOURCHETTES_NIVEAU` |
| 4. Niveau fiabilisé | Croise le niveau saisi et celui du libellé, retient un niveau, et dit s'il est sûr ou incertain. | `decider_niveau`, `ARRONDI_NIVEAU` |
| 5. École et type de diplôme | Décode l'école et en déduit le type de diplôme : ingénieur, commerce, université ou autres. | `ref_ecoles.xlsx`, `CATEGORIE_PAR_DEFAUT` |
| 6. Dédoublonnage | Retire les répétitions en gardant la ligne la mieux renseignée. Signale les quasi-doublons sans les retirer. | `CLES_DOUBLON` |
| 7. Contrôles et statut | Donne un statut à chaque ligne et contrôle les dates de diplôme. | `CONTROLES`, `PRIORITE_STATUT` |
| 8. Vue par salarié | Une ligne par salarié : niveau le plus élevé, type de diplôme, compteur, commentaire. | `CATEGORIE_SI_AMBIGU` |
| 9. Export | Écrit les deux fichiers Excel, mis en forme. | `SORTIES`, `BLOCS` |

## Les règles principales

**L'échelle des niveaux**

| Niveau | Ce qu'il regroupe |
|---|---|
| BAC MAX | Le bac ou moins : secondaire, CAP, niveau bac, baccalauréat. |
| BAC+2 | DEUG, DUT, BTS, technicien spécialisé, classes préparatoires, brevet bancaire. |
| BAC+3 | Licence, bachelor en 3 ans. |
| BAC+4 | Master 1, maîtrise, licence avant 2006, cycle normal, ITB. |
| BAC+5 | Master, diplôme d'ingénieur, grande école, DESS, DEA. BAC+6 a le même rang. |
| BAC+7 | Doctorat, expertise comptable. |
| Autres (hors échelle) | Certificats, MBA, executive : ils ne comptent pas pour le niveau le plus élevé. Exception : l'executive master en management bancaire, compté BAC+5. |

**Quand la saisie et le diplôme ne disent pas la même chose**, on retient le plus bas des deux niveaux, et la ligne garde une réserve : on ne sait pas lequel a raison. Un niveau « Bac+5 et plus » est ramené à BAC+5, le niveau sûr, avec un signal.

**Le type de diplôme** : le libellé d'abord (« Diplôme d'ingénieur »), sinon la nature de l'école (un master d'une école de commerce est un diplôme de commerce). Un « Master » sans école connue est classé par défaut, et son type est dit incertain.

**Les écoles** : chaque code est décodé dans `ref_ecoles.xlsx`. Aucun rapprochement automatique entre noms proches : ENSA et ENSAM restent deux écoles. Le pays est écrit sur chaque diplôme, ou `INCONNU` quand on ne le connaît pas.

**Les doublons** : la ligne la mieux renseignée est gardée. Deux diplômes différents ne sont jamais fusionnés. Un quasi-doublon (même diplôme, mais deux écoles ou deux spécialités) garde ses deux lignes, signalées.

**Les dates de diplôme** : une date illisible, avant les 14 ans du salarié, dans le futur, ou différente d'une ligne à l'autre est signalée. Cela ne change ni le niveau ni le type de diplôme.

**Le niveau du salarié** : le plus élevé de ses lignes. S'il vient d'un choix de la fiabilisation, il est retenu avec réserve. Sans aucune ligne avec un niveau, le salarié est `NON DETERMINE`.

Le détail de chaque règle, avec ses exemples, est écrit dans le notebook, au début de chaque étape.

## Lire la vue par salarié

`Vue_salarie` contient **tous** les salariés, une ligne chacun. Deux colonnes servent à la lire :

- **`nb_lignes_a_traiter`** est le filtre. À `0`, le niveau et le type de diplôme sont sûrs : le salarié s'utilise sans relecture. Sans ce filtre, la vue contient aussi des niveaux retenus avec réserve et des salariés sans niveau.
- **`commentaire`** dit en une phrase pourquoi le salarié a ce niveau et ce type de diplôme, ou ce qui a empêché de les trouver. Il commence toujours par l'un de quatre débuts, à filtrer dans Excel avec « commence par » :

| Début du commentaire | Ce que ça veut dire |
|---|---|
| `Niveau et catégorie sûrs` | Tout est bon. Compteur à `0`. |
| `Niveau retenu avec réserve (…)` | Le niveau vient d'un choix de la fiabilisation, expliqué à la suite. |
| `Niveau sûr (…), catégorie incertaine` | Le niveau est bon, le type de diplôme est en doute. |
| `Aucun diplôme avec un niveau` | Le salarié est `NON DETERMINE`. |

Dans les fichiers, les colonnes fiabilisées sont en vert clair : ce sont celles à utiliser. La colonne s'appelle `categorie` dans le notebook ; dans les présentations et le rapport, on dit « type de diplôme ».

## Relancer sur une nouvelle extraction

Après un lancement, trois listes signalent les nouveautés. Ce sont les seules qui demandent une décision :

| Liste | Ce qu'elle contient | Où corriger |
|---|---|---|
| Niveaux inconnus | Une écriture du niveau jamais vue | `NIVEAUX_ECRITS`, étape 2 |
| Libellés non classés | Un diplôme que les règles ne reconnaissent pas | `REF_DIPLOMES_MANUEL` ou `REGLES_DIPLOME`, étape 3 |
| Écoles hors référentiel | Un code d'école à décoder | `ref_ecoles.xlsx` |

Ensuite, dans le fichier de détail, l'onglet `A_traiter` liste les lignes et l'onglet `Salaries_a_discuter` les salariés qui demandent un retour au dossier.

## À quoi sert la base

La base donne le niveau d'études de chaque salarié, avec une indication de confiance. Elle peut servir à toute analyse RH qui en a besoin.

Son premier usage est le projet de détection des anomalies de rémunération, qui lit deux colonnes de la vue par salarié : `Niveau_Etude_Max` et `Cat_Ecole_Max`. Ce qu'il en fait est décrit dans le [README de ce projet](../README.md), pas ici.

## Données et confidentialité

- Les deux extractions du dossier ont des matricules fictifs : elles sont dans le dépôt.
- L'extraction réelle porte des noms, des prénoms et des dates de naissance. Elle se pose dans ce dossier sur le poste, et **elle n'est jamais envoyée en ligne**, pas plus que les deux fichiers que le notebook en tire (`.gitignore`).
- Le dossier `documents/` reste lui aussi sur le poste.
- Les tableaux affichés dans le notebook suivi par git viennent toujours de l'extraction fictive.

## Feuille de route

| Chantier | Statut |
|---|---|
| D1. Explorer l'extraction et poser la démarche (19 au 21/10) | Terminé |
| D2. Arrêter les règles avec la hiérarchie (26/10 au 02/11) | Terminé |
| D3. Rendre la démarche reproductible : notebook v13, référentiel des écoles en Excel (02 au 09/11) | Terminé |
| D4. Livrer une vue par salarié, avec un compteur qui sert de filtre (09 au 12/11) | Terminé |
| D5. Passer sur les données réelles et restituer (23/11) | Terminé |
| D6. Mettre le projet à part (27/11) | Terminé |
| D7. Arbitrer ce qui reste à traiter, dossier du salarié à l'appui | À lancer |
| D8. Faire vivre la base : correction à la source, prochaine extraction | À décider |

Trois décisions sont attendues pour lancer D7 et D8 : valider les correspondances (niveaux, types de diplôme, écoles), désigner qui arbitre les cas à discuter, et dire si les corrections sont reportées dans le SIRH.

Le détail (plan d'actions, relevé de décisions, points ouverts chiffrés) est dans le classeur de `documents/1 - Feuille de route`. L'historique des changements, commit par commit, est dans la chronologie du [README du projet](../README.md).
