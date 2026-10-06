# Chronologie du projet

Le projet repart du code d'origine et le réécrit fichier par fichier.

| Commit      | Titre                                                         | En bref                                                                                                                                                           |
| ----------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`c75df63`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/c75df63690e7568fdc533a11606666ba61075a63) | docs: ajouter la chronologie des commits | `README.md` : ce tableau, affiché sur la page d'accueil, qui suit les commits du plus ancien au plus récent. |
| [`640a545`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/640a545de1440e2eaac34aca2049c0c658fab7b0) | chore: enregistrer le code d'origine, sans correction         | Le code d'origine, gardé tel quel dans `archive/`.                                                                                                              |
| [`1da24e1`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/1da24e1948a8f3ce2394543e502d84bf0d0fd461) | feat: préparer le tableau des salariés (prétraitement)     | `src/anomaly_pretraitement.py` : lit les trois fichiers d'entrée, retire les doublons, ajoute la fourchette de la grille, le salaire du marché et les ratios. |
| [`8bdea95`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/8bdea95ce3fb3aad7e9aa5bbdb1247271e4faf0a) | feat: ajouter le générateur de données salariales fictives | `src/generate_sources.py` et les trois fichiers de `input/` : 10 000 salariés.                                                                               |
| [`4999a33`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/4999a33b793d0910f9089711e97b032d7e4fbf5c) | feat: former les groupes de collègues (cohortes) | `src/anomaly_cohortes.py` : compare chaque salarié à un groupe d'au moins 15 collègues comparables (même grade, même métier, ancienneté proche) et mesure son écart au groupe (PeerZ). |
| [`6872cef`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/6872cef7616f720b16cf2159d807cc4b5ce23ea3) | feat: repérer les salaires hors des clous (règles) | `src/anomaly_regles.py` : applique quatre règles (hors grille, CompaRatio, marché, écart aux collègues) et ajoute à chaque salarié ses alertes, ses points et ses motifs. |
| [`8bd99ee`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/8bd99eefc8d0927c063f3ea10eab6e0c9556c485) | feat: repérer les profils atypiques avec l'IA (Isolation Forest) | `src/anomaly_signal_iforest.py` : donne à chaque salarié un score d'anomalie de 0 à 100 (ML_AnomalyScore), calculé par l'IA sur tout son profil. |
| [`b140977`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b14097743eb739791ecf374481518ce8c7103131) | feat: signaler les profils que seule l'IA repère (signal fort) | `src/anomaly_signal_fort.py` : donne l'étiquette ML_STRONG_SIGNAL et 15 points aux 5 % de profils les plus atypiques pour l'IA qui n'ont déclenché aucune règle. |
| [`c294ed6`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/c294ed6a8702a6781864d15287c1ff10e8812128) | feat: recommander un ajustement et en chiffrer le coût (recommandations) | `src/anomaly_recommandations.py` : donne à chaque salarié une recommandation (ajuster au MIN, vers le MID, ou revue) et le coût de l'ajustement. |
| [`f3d2276`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/f3d227696940cd52c47454968164fa714fc00409) | feat: comparer les salaires des femmes et des hommes (écarts hommes/femmes) | `src/anomaly_ecarts_hommes_femmes.py` : compare, pour chaque métier + grade, le salaire médian des femmes et des hommes (rapport M_div_F). |
| [`b7de521`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b7de521eb7ac77b99aff707a1da26b50e5fab630) | feat: calculer le score général et la priorité de chaque salarié | `src/anomaly_score_general.py` : réunit le score des règles (70 %) et celui de l'IA (30 %) en un score général, et en déduit la priorité de chaque salarié (Critical, Major, Minor, Info). |
| [`19abd86`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/19abd860f55769d4d05ed3796ed4e6460514dc32) | feat: créer le tableau de bord HTML | `src/generate_dashboard_html.py` : page web qui résume les résultats (priorités, pôles, métiers, coûts, signaux, score général, écarts hommes/femmes), avec la liste des salariés au clic. |
| [`237159e`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/237159e34cdc9ce93bd7a86d3aa591ea4d9a73b7) | feat: enchaîner toutes les étapes (programme principal) | `src/detect_salary_anomalies.py` : enchaîne toutes les étapes et enregistre anomalies.csv, gender_gap.csv et le tableau de bord. |
| [`b90d769`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b90d76925316b7d929371518727aaa89358abdb2) | feat: vérifier un salaire proposé avec une régression | `src/anomaly_signal_regression.py` : prédit le salaire attendu d'un nouvel embauché ou d'un salarié revu, et signale un salaire proposé trop éloigné (en dehors du programme principal). |
| [`860df00`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/860df003137c727fdacd0ca1a6569cea9a0dbe2f) | chore: enregistrer les résultats de toutes les étapes (output/) | `output/` : les résultats de chaque étape (CSV pour Excel) et le tableau de bord, produits avec le code du dépôt. |
| [`8f35e12`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/8f35e129adad236be679a67717e8962aaf98379b) | refactor: écrire plus clairement l'attribution des priorités | `src/anomaly_score_general.py` : même calcul des priorités, écrit en trois temps nommés et commentés. |
| [`b01f627`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b01f627a70164157bad29da82820cd6858ba3fda) | refactor: parcourir les priorités dans l'ordre du fichier de règles | `src/anomaly_score_general.py` et `config/rules.yaml` : les niveaux de priorité sont rangés du plus bas au plus haut dans le fichier de règles, et le code les suit dans cet ordre (même résultat). |
| [`526938e`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/526938ed3873896f0ca3b50e77dcc0624aff044a) | feat: ajouter l'aide à la décision salariale (application locale) | `decision_support/` : petite application web qui vérifie un salaire ou propose une fourchette et une cible, à partir de la grille, du marché, des groupes de collègues et des règles du programme principal. |
| [`7b625cc`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/7b625cc9ac208f36ba035f9d59ba4676f6cec299) | docs: mettre à jour la capture d'écran de l'aide à la décision | `decision_support/static/apercu.png` : la capture d'écran montre la page avec les chiffres que l'application calcule aujourd'hui. |
| [`2250596`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/2250596a06da624b071cf82b8964d9cb1ce9ab08) | docs: expliquer comment lancer le projet | `README.md` et `requirements.txt` : la partie « Lancer le projet » ci-dessous (installer l'environnement, déposer les trois fichiers dans `input/`, tout lancer d'un coup ou étape par étape) et la liste des bibliothèques à installer. |
| [`8df2cc8`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/8df2cc8b5e2c97e2f12ee51c3c19b6b896bd7d6b) | feat: revoir le tableau de bord (écarts hommes/femmes par grade, trois courbes de score, nom daté) | `src/generate_dashboard_html.py` : écarts hommes / femmes lisibles (axes titrés, sens de lecture, écart écrit au bout de chaque barre, nombre de femmes et d'hommes) avec un bouton par grade ; score général en trois courbes (général, règles, IA) ; tableau de bord enregistré dans `output/dashboard/` sous un nom daté, aussi par le programme principal. |
| [`0893e42`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/0893e42274181ebe771c5b437c1f182605deb85f) | feat: suivre l'avancement dans le terminal | `src/detect_salary_anomalies.py` : quand on lance tout, le terminal affiche chaque étape au moment où elle commence (`[4/9] ...`), le temps qu'elle a pris, puis la durée totale et l'endroit des résultats. |
| [`987bf25`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/987bf25c8c6826b463bf7f7d17c6c568ebace80e) | chore: remplacer les anciens tableaux de bord par le tableau de bord daté | `output/dashboard/` : le tableau de bord daté, produit avec le code du dépôt, remplace les deux anciens tableaux de bord sans date. |
| [`31c89a2`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/31c89a28bdd97df580845a48702b63a6d6624bc7) | feat: faire du signal fort un cinquième signal, sans points | `src/anomaly_signal_fort.py` et `config/rules.yaml` : les 5 % de profils les plus atypiques pour l'IA reçoivent l'étiquette ML_STRONG_SIGNAL et son motif, en plus des signaux des règles, sans aucun point dans le score. |
| [`bff4966`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/bff49667d0eea9c83cf3a48dff36a6ce81f4ce4c) | chore: mettre à jour les résultats après le changement du signal fort | `output/` : les CSV des étapes touchées par le signal fort et le tableau de bord daté qui va avec, refaits avec le code du dépôt. |
| [`4e5c682`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/4e5c682d3d4c5f47ab11be2b29854b9b106361d9) | feat: explorer les données pour choisir la régression (notebook) | `notebooks/exploration_regression.ipynb` : lit les trois fichiers d'entrée et montre en graphes ce qui fait le salaire (log ou pas, grade, métier, âge, ancienneté, compétence, 9-Box, Hot_job…), pour choisir les colonnes et le seuil de la régression. |
| [`84298d2`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/84298d2938957bab7ea932956a54acf80a009c63) | feat: simplifier la régression (80 % pour apprendre, 20 % pour vérifier, une fourchette) | `src/anomaly_signal_regression.py` : le modèle apprend sur 80 % des salariés, il est vérifié sur les 20 % restants, puis il prédit un salaire avec une fourchette ; la vérification d'un salaire proposé (Reg_Z) est retirée. |
| [`0e5e0d2`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/0e5e0d2fe0a8f7e834911f2658465f521526180a) | feat: enregistrer les résultats en fichiers Excel (.xlsx) au lieu de CSV | Les huit étapes de `src/` et le programme principal enregistrent leurs résultats en fichiers Excel (`.xlsx`) au lieu de CSV ; `requirements.txt` ajoute openpyxl. |
| [`7388582`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/738858237ab0b356b72d04a18be08a7f21f7b59e) | feat: ajouter la règle du salaire minimum (un plancher par grade) | `src/anomaly_regles.py` et `config/rules.yaml` : une cinquième règle, MIN_SALARY (20 points), signale les salaires sous le plancher de leur grade, réglé dans `min_salary_by_grade`. |

# Lancer le projet

Toutes les commandes se tapent dans un terminal (PowerShell sous Windows) ouvert dans le dossier du projet.

## 1. Installer l'environnement (une seule fois)

Il faut Python 3.10 ou plus récent ([python.org](https://www.python.org/downloads/) ; sous Windows, cocher « Add python.exe to PATH » pendant l'installation).

L'environnement virtuel est un dossier `.venv`, propre au projet, où sont installées les bibliothèques de `requirements.txt` sans toucher au reste de l'ordinateur.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Quand `(.venv)` s'affiche au début de la ligne, l'environnement est actif. Dans chaque nouveau terminal, il suffit de refaire la deuxième ligne.

- Si PowerShell refuse `Activate.ps1` (« l'exécution de scripts est désactivée »), taper une fois `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, puis recommencer.
- Sous macOS ou Linux : `python3 -m venv .venv`, puis `source .venv/bin/activate`.

## 2. Déposer les trois fichiers d'entrée

Les trois fichiers vont dans `input/`, avec exactement ces noms :

```text
input/
├── employes.csv   les salariés : une ligne par salarié
├── bands.csv      la grille interne : une ligne par métier + grade
└── market.csv     le marché : une ligne par métier + grade
```

Le dépôt contient déjà trois fichiers fictifs (10 000 salariés) : le projet se lance tel quel. Pour analyser de vraies données, il suffit de les remplacer.

Format des trois fichiers :

- la première ligne donne les noms des colonnes, écrits exactement comme ci-dessous (l'ordre des colonnes n'a pas d'importance) ;
- les nombres décimaux s'écrivent avec un point : `238.34`, pas `238,34` ;
- le métier (`Job_Family`) et le grade (`Grade`) s'écrivent de la même façon dans les trois fichiers : c'est grâce à eux que chaque salarié retrouve sa grille et son marché. Un salarié dont le métier + grade manque dans la grille reste dans l'analyse, mais sans fourchette.

Pour voir à quoi un fichier doit ressembler, ouvrir un des fichiers fournis avec le Bloc-notes.

**`employes.csv`**

| Colonne | Contenu | Exemple |
| --- | --- | --- |
| `Matricule` | identifiant du salarié (en cas de doublon, la première ligne est gardée) | `Mat00001` |
| `Nom` | nom (peut rester vide) | |
| `Entite_N1` | pôle | `Pole 3` |
| `Entite_N2` | entité dans le pôle | `P3-E05` |
| `Job_Family` | métier | `RETAIL BANKING` |
| `Job_Title` | poste | `JT1389` |
| `Grade` | grade | `5` |
| `Fixe_Annuel_MAD` | salaire fixe annuel, en kMAD | `238.34` |
| `Age` | âge, en années | `28` |
| `Anciennete` | ancienneté, en années | `8` |
| `Sexe` | `F` ou `M` (exactement) | `F` |
| `Competence_N1` | note de compétences de l'année précédente | `4.09` |
| `Positionnement_9BOX` | case de la grille 9Box | `6` |
| `Hot_job` | tension du métier sur le marché, de 0 (faible) à 6 (forte) | `4` |

Les colonnes `Pays`, `FTE`, `Devise` et `Date_Effet_Paie` du fichier fourni ne servent à aucun calcul : elles sont simplement recopiées dans les résultats.

**`bands.csv`** : `Job_Family`, `Grade`, puis `Min`, `Mid` (milieu) et `Max` de la grille, en kMAD.

**`market.csv`** : `Job_Family`, `Grade`, puis `Median`, la médiane du marché, en kMAD. Les colonnes `P25` et `P75` du fichier fourni ne servent pas.

## 3. Tout lancer d'un coup

```powershell
python src/detect_salary_anomalies.py
```

Pendant le calcul, le terminal affiche chaque étape au moment où elle commence (`[4/9] Score de l'IA (Isolation Forest)...`), puis le temps qu'elle a pris. À la fin, il donne la durée totale et l'endroit où trouver les résultats.

Les résultats arrivent dans `output/detection/` :

- `anomalies.xlsx` : un salarié par ligne, avec son score, sa priorité, ses motifs et la recommandation (à ouvrir avec Excel) ;
- `gender_gap.xlsx` : les écarts de salaire femmes / hommes, par métier + grade.

Le tableau de bord arrive dans `output/dashboard/`, sous un nom qui porte la date et l'heure du lancement, par exemple `dashboard_anomalies_2026-10-02_14-35-08.html`. Chaque lancement ajoute un fichier sans effacer les précédents ; le plus récent est le dernier de la liste. Il s'ouvre avec un navigateur (double-clic).

## 4. Lancer étape par étape

Chaque étape se lance seule : elle refait d'elle-même les étapes dont elle a besoin, puis enregistre son propre résultat. On peut donc lancer directement celle qu'on veut regarder. L'ordre ci-dessous est celui du programme principal.

| Ordre | Commande | Ce que l'étape ajoute | Résultat |
| --- | --- | --- | --- |
| 1 | `python src/anomaly_pretraitement.py` | grille, marché et ratios de chaque salarié | `output/pretraitement/employes_pretraites.xlsx` |
| 2 | `python src/anomaly_cohortes.py` | groupe de collègues et écart au groupe (PeerZ) | `output/cohortes/cohortes_salaries.xlsx` |
| 3 | `python src/anomaly_regles.py` | alertes des cinq règles et leurs points | `output/regles/employes_regles.xlsx` |
| 4 | `python src/anomaly_signal_iforest.py` | score de l'IA, de 0 à 100 | `output/signal_iforest/employes_signal_iforest.xlsx` |
| 5 | `python src/anomaly_signal_fort.py` | signal ML_STRONG_SIGNAL pour les 5 % de profils les plus atypiques pour l'IA (sans points) | `output/signal_fort/employes_signal_fort.xlsx` |
| 6 | `python src/anomaly_score_general.py` | score général et priorité | `output/score_general/employes_score_general.xlsx` |
| 7 | `python src/anomaly_recommandations.py` | recommandation et coût de l'ajustement | `output/recommandations/employes_recommandations.xlsx` |
| 8 | `python src/anomaly_ecarts_hommes_femmes.py` | écarts femmes / hommes par métier + grade | `output/ecarts_hommes_femmes/gender_gap.xlsx` |
| 9 | `python src/generate_dashboard_html.py` | tableau de bord | `output/dashboard/dashboard_anomalies_<date>_<heure>.html` |

Les seuils des règles, les poids et les niveaux de priorité se règlent dans `config/rules.yaml`. Après une modification, relancer la commande.

## 5. En dehors du programme principal

| Commande | Ce qu'elle fait |
| --- | --- |
| `python src/anomaly_signal_regression.py` | entraîne les deux modèles de régression (nouvel embauché, salarié revu) sur 80 % des salariés, les vérifie sur les 20 % restants, les enregistre dans `models/` et affiche deux exemples de salaire prédit avec sa fourchette. |
| `python -m pip install -r requirements-notebook.txt` | installe, une seule fois, ce qu'il faut pour relancer [`notebooks/exploration_regression.ipynb`](notebooks/exploration_regression.ipynb) : les graphes qui aident à choisir les colonnes de la régression. Ensuite, ouvrir le notebook dans VS Code et choisir `.venv` comme noyau (« Select Kernel »). Les graphes sont déjà enregistrés dedans : pour seulement les lire, il n'y a rien à installer. |
| `python -m decision_support.app` | ouvre l'aide à la décision sur **http://127.0.0.1:8765** (arrêter avec `Ctrl+C`) ; mode d'emploi dans [`decision_support/README.md`](decision_support/README.md). |
| `python src/generate_sources.py` | fabrique de nouvelles données fictives. **Attention :** il réécrit les trois fichiers de `input/` et remplace donc les vôtres. |

<!--
Modèle à recopier à la fin du fichier pour chaque nouvel envoi.
Avant d'envoyer, « git log --oneline origin/main..HEAD » liste les commits qui vont partir.

## JJ/MM/AAAA — Titre court de l'envoi

Une phrase : ce que cet envoi apporte.

| Commit | Titre | En bref |
|---|---|---|
| [`abc1234`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/abc1234) | feat: ... | ... |
-->
