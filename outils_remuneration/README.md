# Les outils de la rémunération, dans un dossier qui marche tout seul

Ce dossier est une capsule : il contient tout ce qu'il faut pour faire les trois parties du projet, plus la régression. On peut le copier seul sur un autre PC, il n'a besoin de rien d'autre.

1. **Explorer les données** : la page d'exploration (`visualisation/`).
2. **Détecter les anomalies** : la détection et son tableau de bord (`detection/`).
3. **Décider d'un salaire** : l'aide à la décision (`decision_support/`).

Et la **régression des salaires** : trois notebooks, qui rassemblent ce qui était dans trois notebooks séparés du projet (`Prediction_Compa_Ratio`, `Regression_Sans_Anomalies`, `Prediction_Par_Cohorte`). Ils travaillent sur **le même tableau** : les mêmes salariés, les mêmes colonnes, les mêmes modèles. Leurs réglages sont écrits une seule fois, dans `reglages.py`.

Tout lit les mêmes données (`input/`) et les mêmes réglages de la détection (`config/rules.yaml`).

Le dossier s'appelait `regression_salaires` jusqu'au 20/11/2026 : il ne contenait alors que la régression.

## Ce qu'il y a dans le dossier

```
outils_remuneration/
├── lancer_interface.bat             double-clic : refait la détection, ouvre l'écran d'accueil et ses trois outils
├── lancer_notebooks.bat             double-clic : ouvre le dossier dans le navigateur, pour lancer les notebooks
├── requirements.txt                 les bibliothèques Python à installer (les deux .bat s'en occupent)
│
├── input/                           LES DONNÉES : employes.xlsx, bands.xlsx, market.xlsx
├── config/rules.yaml                les réglages de la détection (seuils, poids, priorités)
│
├── detection/                       la détection d'anomalies, le tableau de bord et l'écran d'accueil
│                                    (12 fichiers recopiés de src/, sans y toucher)
├── visualisation/                   la page d'exploration des données
├── decision_support/                l'aide à la décision, et le programme qui sert toute l'interface
├── accueil/                         les trois images de l'écran d'accueil
│
├── reglages.py                      TOUS les réglages de la régression, à un seul endroit
├── preparation.py                   fabrique le tableau des salariés (commun aux trois notebooks)
├── modeles.py                       les six modèles (communs aux notebooks 2 et 3)
├── 1_Visualisations.ipynb           avant de prédire : anomalies, valeurs aberrantes, corrélations
├── 2_Prediction.ipynb               les six modèles, les métriques, les graphes, la validation croisée
├── 3_Prediction_Par_Cohorte.ipynb   les mêmes modèles, appris cohorte par cohorte
│
├── accueil.html                     l'écran d'accueil, refait à chaque détection
├── output/                          les résultats de la détection et les tableaux de bord
├── models/                          le modèle de la régression de la détection
└── resultats/                       les fichiers Excel écrits par les notebooks
```

Les quatre derniers n'existent pas dans un dossier tout neuf : ils sont créés au premier lancement.

## L'interface : les trois outils

Double-cliquer sur `lancer_interface.bat`. Il installe ce qui manque, refait la détection sur les fichiers de `input/`, puis ouvre l'écran d'accueil dans le navigateur, avec une carte par outil. La première fois, il crée un Python propre au dossier (sous-dossier `.venv`) et installe les bibliothèques : compter quelques minutes.

- **Passer d'un outil à l'autre** : cliquer sur « Repères », en haut à gauche de chaque page. On revient à l'écran d'accueil.
- **Après avoir remplacé les fichiers de `input/`** : cliquer sur « Refaire la détection », en haut du tableau de bord. Le nouveau tableau de bord s'affiche, et l'écran d'accueil et l'aide à la décision passent aussi aux nouveaux fichiers.
- **La fenêtre noire doit rester ouverte** : la fermer arrête l'interface.

Les fichiers Excel de la détection arrivent dans `output/detection/` (`anomalies.xlsx`, `gender_gap.xlsx`). Les seuils, les poids et les priorités se règlent dans `config/rules.yaml`.

Les fichiers de `detection/`, `visualisation/`, `decision_support/` et `accueil/` sont des copies de ceux du projet. Dans `detection/`, les commentaires parlent encore de `src/` : c'est le nom de ce dossier dans le projet. Deux fichiers seulement diffèrent du projet, d'une ligne chacun, pour chercher la détection dans `detection/` au lieu de `src/` : `decision_support/app.py` et `decision_support/engine.py`.

## La régression : les trois notebooks

### Dans quel ordre

1. **Les données** : mettre les trois fichiers Excel dans `input/`, à la place de ceux qui y sont (mêmes noms : `employes.xlsx`, `bands.xlsx`, `market.xlsx`).
2. **Régler** : ouvrir `reglages.py` et vérifier les anomalies à retirer et les colonnes.
3. **Regarder** : lancer `1_Visualisations`. Il montre qui est retiré, où sont les valeurs aberrantes, et quelles colonnes sont liées au salaire. Si une colonne ne sert à rien, on la met de côté dans `reglages.py` et on relance.
4. **Prédire** : lancer `2_Prediction`. Il lit les mêmes réglages : pas besoin de les recopier.
5. **Par cohorte** (si besoin) : lancer `3_Prediction_Par_Cohorte`. Il est long, parce qu'il refait les six modèles pour chaque façon de former les cohortes.

Les notebooks 2 et 3 n'ont pas besoin que le notebook 1 ait tourné avant : chacun refabrique le tableau lui-même.

### Lancer

Double-cliquer sur `lancer_notebooks.bat`. Il se sert du même Python (`.venv`) que `lancer_interface.bat` : si l'un des deux a déjà tourné, l'autre ouvre tout de suite.

Le dossier s'ouvre dans le navigateur : on clique sur le notebook voulu, puis sur « Run », « Run All Cells ».

Il faut un Python 3.10 à 3.13 sur le PC. Dans VS Code, on ouvre directement le notebook.

## Les réglages (`reglages.py`)

| Réglage | Ce qu'il fait | Au départ |
|---|---|---|
| `DOSSIER` | le dossier des trois fichiers Excel | `'input'` |
| `A_RETIRER` | les priorités de la détection qu'on retire : `Critical`, `Major`, `Minor`, `Info`, ou `Outlier positif` (un salarié sans alerte payé au-dessus du Max de sa grille). `[]` : personne n'est retiré, tous les salariés servent | `['Critical', 'Outlier positif']` |
| `ENLEVER` | `True` : une ligne qui a une valeur aberrante est écartée. `False` : elles restent | `False` |
| `COLONNES_RETRAIT` | les colonnes où l'on cherche les valeurs aberrantes | Compa-Ratio, âge à l'embauche, compétence |
| `COLONNES` | les colonnes que les modèles reçoivent. Un `#` devant une ligne la met de côté | 8 colonnes |
| `BUCKETS_ANCIENNETE`, `BORNES_ANCIENNETE` | l'ancienneté en tranches, en plus | `False` |
| `PROFONDEUR` | la profondeur de l'arbre de décision | `5` |
| `LOG_SALAIRE`, `LOG_COMPA_RATIO` | le salaire et le Compa-Ratio appris en logarithme | `True`, `True` |
| `EN_PLUS_POUR_LE_SALAIRE` | les colonnes données en plus aux modèles du salaire | `['Mid']` |
| `PAQUETS` | le nombre de paquets de la validation croisée | `5` |

`A_RETIRER` et `ENLEVER` ne retirent pas les mêmes salariés :

* une **anomalie** vient de la détection (un salaire trop bas pour le poste, par exemple) ;
* une **valeur aberrante** (outlier) vient seulement de la boîte à moustaches : une valeur très loin des autres dans une colonne.

Les cohortes (`COHORTES`, `TAILLE_MIN`) ne servent qu'au notebook 3 : elles se règlent dedans, à son étape 2.

**Après un changement dans `reglages.py`** : enregistrer le fichier, puis relancer le notebook depuis sa première cellule. Pas besoin de fermer le notebook : sa première cellule relit le fichier.

Pour modifier `reglages.py` sans VS Code : dans la page ouverte par `lancer_notebooks.bat`, cliquer sur `reglages.py`. Il s'ouvre dans le navigateur, on le modifie, puis Ctrl+S.

## Les fichiers écrits

Tous dans `resultats/` :

| Fichier | Écrit par | Contenu |
|---|---|---|
| `anomalies.xlsx` | `1_Visualisations` | le résultat complet de la détection, pour tous les salariés |
| `salaries_retires.xlsx` | `1_Visualisations` | les anomalies retirées, avec ce que la détection dit d'elles |
| `resultats_prediction.xlsx` | `2_Prediction` | les salariés du test, avec le vrai salaire, le salaire prédit et l'erreur de chaque modèle |

## Ce qui est recopié du projet

Les 12 fichiers de `detection/` et `config/rules.yaml` sont des copies exactes de ceux du projet (`src/` et `config/rules.yaml`) : 8 faites le 19/11/2026, puis 4 le 20/11/2026 pour l'interface (le programme principal, les écarts femmes / hommes, le tableau de bord, l'écran d'accueil). `visualisation/`, `decision_support/` et `accueil/` ont été recopiés le 20/11/2026. C'est ce qui permet au dossier de marcher seul.

À savoir : si le projet change, ce dossier ne suit pas tout seul. Il faut recopier les fichiers ici, en gardant les deux lignes de `decision_support/` qui cherchent la détection dans `detection/`.

## Retrouver les chiffres des anciens notebooks du projet

| Pour retrouver | Réglages |
|---|---|
| `Prediction_Compa_Ratio` | `A_RETIRER = []`, et le même `ENLEVER` que dans ce notebook |
| `Regression_Sans_Anomalies` | `A_RETIRER = ['Critical', 'Outlier positif']`, `ENLEVER = False` |
| `Prediction_Par_Cohorte` | les mêmes que ci-dessus, dans `3_Prediction_Par_Cohorte` |

Dans le notebook 3, la ligne « Sans cohorte » des tableaux redonne les chiffres du notebook 2.
