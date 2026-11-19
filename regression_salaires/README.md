# La régression des salaires, dans un dossier qui marche tout seul

Ce dossier est une capsule : il contient tout ce qu'il faut pour regarder les données, puis prédire le salaire. On peut le copier seul sur un autre PC, il n'a besoin de rien d'autre.

Il rassemble ce qui était dans trois notebooks séparés du projet (`Prediction_Compa_Ratio`, `Regression_Sans_Anomalies`, `Prediction_Par_Cohorte`).

Les trois notebooks du dossier travaillent sur **le même tableau** : les mêmes salariés, les mêmes colonnes, les mêmes modèles. Les réglages sont écrits une seule fois, dans `reglages.py`.

## Ce qu'il y a dans le dossier

```
regression_salaires/
├── lancer_notebooks.bat             double-clic : installe ce qui manque, ouvre le dossier dans le navigateur
├── requirements.txt                 les bibliothèques Python à installer (le .bat s'en occupe)
│
├── input/                           LES DONNÉES : employes.xlsx, bands.xlsx, market.xlsx
│
├── reglages.py                      TOUS les réglages, à un seul endroit
├── preparation.py                   fabrique le tableau des salariés (commun aux trois notebooks)
├── modeles.py                       les six modèles (communs aux notebooks 2 et 3)
│
├── 1_Visualisations.ipynb           avant de prédire : anomalies, valeurs aberrantes, corrélations
├── 2_Prediction.ipynb               les six modèles, les métriques, les graphes, la validation croisée
├── 3_Prediction_Par_Cohorte.ipynb   les mêmes modèles, appris cohorte par cohorte
│
├── detection/                       la détection d'anomalies (8 fichiers recopiés du projet)
├── config/rules.yaml                les réglages de la détection (seuils, poids, priorités)
│
└── resultats/                       les fichiers Excel écrits par les notebooks
```

## Dans quel ordre

1. **Les données** : mettre les trois fichiers Excel dans `input/`, à la place de ceux qui y sont (mêmes noms : `employes.xlsx`, `bands.xlsx`, `market.xlsx`).
2. **Régler** : ouvrir `reglages.py` et vérifier les anomalies à retirer et les colonnes.
3. **Regarder** : lancer `1_Visualisations`. Il montre qui est retiré, où sont les valeurs aberrantes, et quelles colonnes sont liées au salaire. Si une colonne ne sert à rien, on la met de côté dans `reglages.py` et on relance.
4. **Prédire** : lancer `2_Prediction`. Il lit les mêmes réglages : pas besoin de les recopier.
5. **Par cohorte** (si besoin) : lancer `3_Prediction_Par_Cohorte`. Il est long, parce qu'il refait les six modèles pour chaque façon de former les cohortes.

Les notebooks 2 et 3 n'ont pas besoin que le notebook 1 ait tourné avant : chacun refabrique le tableau lui-même.

## Lancer

Double-cliquer sur `lancer_notebooks.bat`. La première fois, il crée un Python propre au dossier (sous-dossier `.venv`) et installe les bibliothèques : compter quelques minutes. Les fois suivantes, il ouvre tout de suite.

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

## La détection, recopiée du projet

Les 8 fichiers de `detection/` et `config/rules.yaml` sont des copies exactes de ceux du projet (`src/anomaly_*.py` et `config/rules.yaml`), faites le 19/11/2026. C'est ce qui permet au dossier de marcher seul.

À savoir : si la détection change dans le projet, ce dossier ne suit pas tout seul. Il faut recopier les fichiers ici.

## Retrouver les chiffres des anciens notebooks du projet

| Pour retrouver | Réglages |
|---|---|
| `Prediction_Compa_Ratio` | `A_RETIRER = []`, et le même `ENLEVER` que dans ce notebook |
| `Regression_Sans_Anomalies` | `A_RETIRER = ['Critical', 'Outlier positif']`, `ENLEVER = False` |
| `Prediction_Par_Cohorte` | les mêmes que ci-dessus, dans `3_Prediction_Par_Cohorte` |

Dans le notebook 3, la ligne « Sans cohorte » des tableaux redonne les chiffres du notebook 2.
