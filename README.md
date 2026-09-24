# Détection des anomalies salariales

Analyse des salaires à partir des grilles internes, du marché et des profils RH.

## Historique du travail

Ce dépôt présente un **historique reconstruit**, créé à partir du script initial, des sources finales et du bilan. Les dates des commits sont celles de la reconstruction. Les étapes intermédiaires ne sont pas des sauvegardes datées retrouvées.

[Parcours des commits et méthode](docs/historique_reconstruit.md). Jalons : `v0.1-moteur`, `v0.2-dashboard`, `v0.3-regression`, `v0.4-decision-support`. Les tests accompagnant les étapes servent à valider leur reconstruction ; leur présence ne prétend pas dater leur écriture originale.

La reconstruction est vérifiée par **139 tests**, les traitements sur **10 000 lignes** et les propositions sur **91 couples métier/grade**. [Détail des vérifications](docs/verification_reconstruction.md).

## Organisation

```text
input/                   Données d'entrée : employés, grilles et marché
config/                  Réglages des deux moteurs
src/                     Code Python
decision_support/        Simulation : évaluer un salaire ou proposer une fourchette
output/
  principal/             Résultats du moteur règles + IA
  regression/            Résultats de la variante avec régression
  classification/        Résultats de l'expérimentation multi-modèles
notebooks/               Notebook d'expérimentation
models/                  Modèles et préprocesseur sauvegardés
tests/                   Tests automatiques
  data/                  Jeu d'exemple pour le débogage des cohortes
docs/                    Bilan du projet, en HTML et Markdown
archive/                 Code initial conservé comme référence
.venv/                   Environnement local à créer (non versionné)
```

Les sorties et modèles sont régénérables et ne sont pas versionnés. Les trois CSV synthétiques de `input/` sont inclus, sans recalcul. Une exécution crée les dossiers de sortie nécessaires.

## Lancer le moteur principal

Depuis la racine du projet, dans PowerShell :

```powershell
.\.venv\Scripts\python.exe src/detect_salary_anomalies_custom_fixed.py --employees input/employes.csv --bands input/bands.csv --market input/market.csv --rulebook config/rules.yaml --output output/principal/anomalies.csv --excel-output output/principal/anomalies.xlsx --gender-output output/principal/gender_gap.csv
```

Le tableau de bord HTML est créé dans `output/principal/`. Ajouter `--no-html` pour le désactiver. Les dossiers de sortie sont créés automatiquement si nécessaire.

Pour le régénérer sans relancer la détection : `.\.venv\Scripts\python.exe src/generate_dashboard_html.py` (relit `anomalies.csv` et `gender_gap.csv`).

Le tableau de bord suit la même charte que l'aide à la décision. Il présente :

- un bandeau d'indicateurs : part de l'effectif à traiter, anomalies critiques, majeures et mineures, coût d'ajustement total ;
- les anomalies à traiter par pôle, les métiers les plus concernés, le coût par pôle, les signaux déclencheurs, la répartition du score de risque (colorée par sévérité) et les écarts hommes/femmes les plus marqués ;
- les données détaillées sous forme de tableaux repliables.

Un clic sur une barre ouvre la liste des salariés concernés, exportable en CSV pour Excel. Les montants restent dans l'unité du fichier source. Les graphiques utilisent Chart.js, chargé depuis Internet : sans connexion, ils ne s'affichent pas (les données restent dans le fichier et ne sont pas envoyées).

## Utiliser l'aide à la décision

```powershell
.\.venv\Scripts\python.exe -m decision_support.app
```

Ouvrir **http://127.0.0.1:8765**. Choisir « Vérifier un salaire » ou « Obtenir une proposition ». Les montants sont en **milliers de MAD par an**. [Mode d'emploi et méthode](decision_support/README.md).

## Lancer la variante avec régression

```powershell
.\.venv\Scripts\python.exe src/detect_salary_anomalies_regression.py --employees input/employes.csv --bands input/bands.csv --market input/market.csv --rulebook config/rules_regression.yaml --output output/regression/anomalies.csv --excel-output output/regression/anomalies.xlsx --gender-output output/regression/gender_gap.csv --reg-gender-output output/regression/reg_gender_gap.csv
```

## Vérifier le projet

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Les tests utilisent leurs propres exemples. Ils ne modifient pas les données d'entrée.

## Consulter et expérimenter

- [Bilan du projet](docs/bilan_evolution_projet.html)
- [Version modifiable du bilan](docs/bilan_evolution_projet.md)
- Tableau de bord principal : `output/principal/dashboard_anomalies.html` (créé après exécution)
- [Notebook multi-modèles](notebooks/anomaly_classification.ipynb)
- [Code initial](archive/detect_salary_anomalies_custom.txt)

Le notebook retrouve la racine du projet depuis `notebooks/` ou depuis la racine. Il lit `input/`, sauvegarde les modèles dans `models/` et les résultats dans `output/classification/`.

`src/generate_sources.py` génère des données de démonstration et **remplace les trois CSV de `input/`**. `src/debug_cohort.py` utilise uniquement le jeu d'exemple de `tests/data/`.

## Environnement

Créer un environnement Python puis installer les dépendances :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Pour le notebook, installer également `requirements-notebook.txt`.

Les entrées du moteur utilisent l'encodage Windows `cp1252`. Les sorties CSV sont en UTF-8. Les montants du jeu actuel sont en **milliers de MAD par an**, unité confirmée par le porteur du projet. Toutes les tables doivent utiliser la même unité.
