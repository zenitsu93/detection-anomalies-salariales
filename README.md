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
| [`d3ec9b7`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/d3ec9b77e515516363f530a97be3e802b65f415d) | feat: tableaux filtrables comme dans Excel et clic sur les nombres de priorité | `src/generate_dashboard_html.py` : tous les tableaux se filtrent comme dans Excel (recherche, tri et filtre par colonne), les nombres Critical, Major, Minor et Info ouvrent la liste de leurs salariés, et cette liste s'exporte en Excel. |
| [`9dd92fa`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/9dd92fa1393f23277c0be65433e42627768b560f) | feat: passer aussi les fichiers d'entrée en Excel (générateur et lecture) | `src/generate_sources.py` et `input/` : le générateur écrit les trois fichiers d'entrée en Excel, et toute la chaîne, l'aide à la décision et le notebook les lisent en Excel (mêmes données). |
| [`fc0893c`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/fc0893cb84d2da083359247145d061fa692ee2f3) | chore: refaire les résultats en Excel avec le code du dépôt | `output/` : les résultats de toutes les étapes en `.xlsx` et le tableau de bord daté qui va avec, refaits avec le code du dépôt. |
| [`c5b96dd`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/c5b96dd1f0a4daba19b6372ec8f3206dbb595ce7) | feat: l'aide à la décision donne le salaire prédit par la régression et contrôle le salaire minimum | `decision_support/` : l'aide à la décision affiche le salaire prédit par la régression et sa fourchette (champs Âge et Hot job pour un nouvel embauché), applique la règle du salaire minimum et ne propose jamais de fourchette sous le plancher du grade. |
| [`6c7ecc2`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/6c7ecc2feb86af3152510e795b89fff0d11bc083) | docs: mettre à jour la capture d'écran de l'aide à la décision | `decision_support/static/apercu.png` : la capture d'écran montre le nouveau bandeau, avec le salaire prédit par la régression. |
| [`5f75537`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/5f755379fe9445b408131c41def7a70b41d229f9) | feat: générer des données fictives avec des anomalies volontaires | `src/generate_sources_anomalies.py` : lance le générateur, puis ajoute des anomalies volontaires (400 salaires hors grille ou très bas, 10 matricules en double) pour que la détection ait de quoi travailler. |
| [`0aa040f`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/0aa040fac847bb64860317c2c53b2602ca0a98c6) | chore: ne plus envoyer input/ et output/ sur GitHub | `.gitignore` : `input/` et `output/` ne sont plus envoyés sur GitHub (pour que de vraies données salariales n'y partent jamais) ; le README dit comment fabriquer les fichiers fictifs. |
| [`2f142a6`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/2f142a6a4ae803b258143fcfbbe2eefb45eb1799) | docs: adapter le notebook à la régression avec fourchette (plus de Reg_Z ni de seuil) | `notebooks/exploration_regression.ipynb` : plus de Reg_Z ni de seuil ; le dernier graphe vérifie que le vrai salaire tombe dans la fourchette 9 fois sur 10, grade par grade. |
| [`6fea0e5`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/6fea0e54132e92724b801d5e16a11da384bcbde7) | feat: ajouter trois graphiques au tableau de bord (coût par action, position dans la grille, carte métier × grade) | `src/generate_dashboard_html.py` : le coût d'ajustement par pôle séparé entre remise au Min et rapprochement du Mid, la répartition des salariés dans leur grille (CompaRatio) avec la zone normale, et une carte métier × grade de la part de salariés à traiter. |
| [`ec734cb`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/ec734cbbb460477e60dbc685727ac09b5e3e22cd) | fix: donner au 9Box les parts de 0 à 6 et ramener le Hot_job de 0 à 2 (données fictives) | `src/generate_sources.py` et `decision_support/` : dans les données fictives, la case 9Box va de 0 à 6 avec les parts réglées (14 %, 6 %, 35 %...), donnée à chaque salarié, et le Hot_job de 0 à 2, un tiers chacun, donné au poste ; l'aide à la décision refuse un Hot job au-dessus de 2. |
| [`53351cc`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/53351cc9ad823abdf8db4e29e20a2339e84e94f7) | docs: relancer le notebook sur les nouvelles données (Hot_job de 0 à 2, 9Box de 0 à 6) | `notebooks/exploration_regression.ipynb` : le texte donne les nouvelles plages du Hot_job et du 9Box, et tous les graphes sont refaits sur les données actuelles. |
| [`5e37024`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/5e370243350fbdb27f7862662e30e7ba23dcd0bc) | refactor: retirer la position dans la grille et la carte métier × grade du tableau de bord | `src/generate_dashboard_html.py` : des trois graphiques ajoutés juste avant, seul le coût d'ajustement par pôle et par action est gardé. |
| [`aaac8c5`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/aaac8c5b26d923dde45a2781587d209151aa885e) | refactor: garder un seul modèle de régression, avec toutes les colonnes du salarié | `src/anomaly_signal_regression.py` et `decision_support/` : plus de modèle à part pour le nouvel embauché ; le salaire prédit est donné pour un salarié existant, avec toutes ses colonnes (ancienneté, compétence, 9-Box…), et l'aide à la décision ne demande plus l'âge ni le Hot job. |
| [`79bed13`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/79bed136f5eb950055f66b091bed69e8a63950c6) | docs: expliquer chaque graphe du notebook en mots simples | `notebooks/exploration_regression.ipynb` : au-dessus de chaque graphe, à quoi il sert, comment le lire et un tableau des formes qu'il peut prendre ; une grande matrice des liens entre toutes les colonnes chiffrées remplace les graphes grille / marché et âge / ancienneté ; nom, pays, FTE, devise et date de paie retirés d'office ; une seule liste de colonnes, lue dans `src/anomaly_signal_regression.py`. |
| [`56062cc`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/56062cc0cfd7f5303ae8c5ae20a20520c339b064) | feat: ouvrir le notebook d'un double-clic, dans le navigateur, avec le Python du projet | `lancer_notebook.bat` : prépare le `.venv` (le refait s'il vient d'un autre PC), installe les bibliothèques et ouvre le notebook dans le navigateur, sans l'extension Jupyter de VS Code ; `notebooks/exploration_regression.ipynb` s'ouvre directement avec le Python du `.venv` et dit en clair ce qui manque quand ce n'est pas le bon Python. |
| [`a5b664d`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/a5b664df3328e5b7dd6415af336a890641398577) | feat: remplacer le notebook par l'analyse du positionnement salarial pour le comité | `notebooks/EDA_Positionnement_Salarial_Comite.ipynb` remplace `notebooks/exploration_regression.ipynb` : contrôle des données, place de chaque salarié dans sa grille et face au marché, ce qui fait varier cette place, colonnes qui disent la même chose (VIF), puis la régression avec, pour chaque colonne, un verdict « garder » ou « retirer ». `lancer_notebook.bat` l'ouvre d'un double-clic, et `requirements-notebook.txt` ajoute statsmodels, dont il a besoin. |
| [`21e748a`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/21e748aaedb28b77635a031036cafe88f91b4fb6) | feat: rendre interactifs les graphes du notebook du comité (zoom, échelle, infos au survol) | `notebooks/EDA_Positionnement_Salarial_Comite.ipynb` : les graphes se manipulent à la souris (zoom, échelle logarithmique, matricule et nom du salarié au survol, image pour le comité) ; textes et calculs inchangés. `requirements-notebook.txt` : plotly remplace matplotlib et seaborn. |
| [`8f6094b`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/8f6094bf79146d0bd0ecf1e3abea829bad2b87c4) | refactor: retirer du notebook du comité la visualisation des effectifs et l'estimation finale | `notebooks/EDA_Positionnement_Salarial_Comite.ipynb` : plus d'histogrammes des effectifs par entité et par poste, ni de régression finale (verdict par variable, comparaison des modèles, table du salaire prédit) ; le notebook s'arrête à la matrice de corrélation et au VIF. |
| [`a9015f8`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/a9015f8e3b3347bc6ef231b10f008befe1378203) | feat: revoir trois graphes du notebook du comité (ancienneté par tranche et par grade, jauge 9-Box inversée, plus d'échelle logarithmique) | `notebooks/EDA_Positionnement_Salarial_Comite.ipynb` : le Compa-Ratio se lit par tranche d'ancienneté (0-2, 3-5, 6-12, 13-20, plus de 20 ans) avec un menu pour choisir un grade ; dans la matrice 9-Box × Hot_job, les cases les plus foncées sont celles des salariés les moins bien placés dans leur grille ; les boutons d'échelle logarithmique sont retirés. |
| [`6769c1c`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/6769c1cedea342a808abbd32da8121ef7f44cbea) | feat: ajouter une page d'exploration des données salariales, qui s'ouvre d'un double-clic | `visualisation/` : une page web qui lit les trois fichiers RH, refait les calculs du notebook du comité dans le navigateur (sans Python ni internet) et montre 11 graphes filtrables, de la masse salariale à l'équité, avec un bouton « Relancer » quand les fichiers changent. Le dossier `visualisation/donnees/`, où l'on dépose les fichiers, n'est pas envoyé sur GitHub. |
| [`a10f0d5`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/a10f0d514cb2ebcbe8c2964ff44028bad081ba17) | feat: voir la liste des salariés en cliquant sur un graphe, comme dans Excel | `visualisation/` : un clic sur une barre, une boîte, une case, une bulle ou un point (ou sur un nombre de salariés des chiffres clés et de la qualité des données) ouvre la liste des salariés concernés, avec recherche, tri et filtre par colonne et export Excel, comme dans le tableau de bord. |
| [`3178fd8`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/3178fd8d2ee9123f371a56b44d804e91f36099d3) | refactor: retirer les blocs « Comprendre ce graphe » de la page d'exploration | `visualisation/exploration_salaires.html` : les 11 blocs déroulants qui expliquaient chaque graphe (objectif, comment lire, pour la régression) sont retirés ; chaque graphe se termine par son constat, et ces explications restent dans le notebook du comité. |
| [`5c4b3ae`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/5c4b3ae7b03de46c8b7e0b65d73b95f136c93fdb) | docs: garder dans la chronologie seulement les changements qui comptent | `README.md` : les petites retouches qui suivent un changement plus grand n'ont plus de ligne dans ce tableau (elles restent dans l'historique de GitHub) ; trois lignes de ce genre sont retirées. |
| [`f17e9d7`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/f17e9d7c1a4a92aafae1b88653a9bb1a57c5b505) | feat: ajouter le notebook de fiabilisation des diplômes, qui s'ouvre d'un double-clic | `fiabilisation_diplomes/` : le notebook qui fiabilise l'extraction des diplômes étape par étape (niveau, libellé, école, doublons, contrôles, puis une ligne par salarié) et écrit `BDD_Diplomes_FINAL.xlsx`, avec l'extraction posée à côté de lui ; son `lancer_notebook.bat` l'ouvre dans le navigateur avec le Python du projet, comme le notebook du comité. |
| [`b19a700`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b19a70062d3e49d7aa0c91427b985da0d077c0c5) | refactor: dire « niveau » au lieu de « grade » dans tout le projet | Tout le projet (code, page d'exploration, tableau de bord, aide à la décision, notebook, `config/rules.yaml`) dit « niveau » au lieu de « grade », jusqu'à la colonne `Niveau` des fichiers d'entrée : les vrais fichiers doivent la renommer aussi. Là où « niveau » voulait déjà dire autre chose, on parle maintenant d'étape (groupes de collègues), de priorité ou d'entité N1/N2. |
| [`9a39ce2`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/9a39ce2b548e37229963766a1e4e89ae467d97d6) | feat: déposer les fichiers dans la page d'exploration, sans autorisation du navigateur | `visualisation/` : la page ne lit plus aucun fichier toute seule et le navigateur ne demande plus d'autorisation. On glisse les trois fichiers dans la zone d'accueil (ou on les choisit avec le bouton), chaque fichier reçu est coché, et un fichier redéposé remplace celui du même nom. La page ne garde plus rien d'une ouverture à l'autre. |

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
├── employes.xlsx  les salariés : une ligne par salarié
├── bands.xlsx     la grille interne : une ligne par métier + niveau
└── market.xlsx    le marché : une ligne par métier + niveau
```

Le dossier `input/` n'est pas envoyé sur GitHub (il est dans `.gitignore`) : de vraies données salariales n'y partent jamais. Pour essayer le projet sans données réelles, fabriquer d'abord trois fichiers fictifs (10 000 salariés, dont quelques anomalies volontaires : salaires hors grille ou très bas, matricules en double) :

```powershell
python src/generate_sources_anomalies.py
```

Pour analyser de vraies données, déposer vos trois fichiers à la place.

Format des trois fichiers :

- ce sont des classeurs Excel (`.xlsx`), dont seule la première feuille est lue ;
- la première ligne donne les noms des colonnes, écrits exactement comme ci-dessous (l'ordre des colonnes n'a pas d'importance) ;
- les salaires, âges et notes sont saisis comme des nombres, pas comme du texte ;
- le métier (`Job_Family`) et le niveau (`Niveau`) s'écrivent de la même façon dans les trois fichiers : c'est grâce à eux que chaque salarié retrouve sa grille et son marché. Un salarié dont le métier + niveau manque dans la grille reste dans l'analyse, mais sans fourchette.

Pour voir à quoi un fichier doit ressembler, ouvrir un des fichiers fictifs avec Excel.

**`employes.xlsx`**

| Colonne | Contenu | Exemple |
| --- | --- | --- |
| `Matricule` | identifiant du salarié (en cas de doublon, la première ligne est gardée) | `Mat00001` |
| `Nom` | nom (peut rester vide) | |
| `Entite_N1` | pôle | `Pole 3` |
| `Entite_N2` | entité dans le pôle | `P3-E05` |
| `Job_Family` | métier | `RETAIL BANKING` |
| `Job_Title` | poste | `JT1389` |
| `Niveau` | niveau | `5` |
| `Fixe_Annuel_MAD` | salaire fixe annuel, en kMAD | `238.34` |
| `Age` | âge, en années | `28` |
| `Anciennete` | ancienneté, en années | `8` |
| `Sexe` | `F` ou `M` (exactement) | `F` |
| `Competence_N1` | note de compétences de l'année précédente | `4.09` |
| `Positionnement_9BOX` | case de la grille 9Box, de 0 à 6 | `6` |
| `Hot_job` | tension du métier sur le marché, de 0 (faible) à 2 (forte) ; la même valeur pour tous les salariés d'un poste | `2` |

Les colonnes `Pays`, `FTE`, `Devise` et `Date_Effet_Paie` du fichier fourni ne servent à aucun calcul : elles sont simplement recopiées dans les résultats.

**`bands.xlsx`** : `Job_Family`, `Niveau`, puis `Min`, `Mid` (milieu) et `Max` de la grille, en kMAD.

**`market.xlsx`** : `Job_Family`, `Niveau`, puis `Median`, la médiane du marché, en kMAD. Les colonnes `P25` et `P75` du fichier fourni ne servent pas.

## 3. Tout lancer d'un coup

```powershell
python src/detect_salary_anomalies.py
```

Pendant le calcul, le terminal affiche chaque étape au moment où elle commence (`[4/9] Score de l'IA (Isolation Forest)...`), puis le temps qu'elle a pris. À la fin, il donne la durée totale et l'endroit où trouver les résultats.

Les résultats arrivent dans `output/detection/` :

- `anomalies.xlsx` : un salarié par ligne, avec son score, sa priorité, ses motifs et la recommandation (à ouvrir avec Excel) ;
- `gender_gap.xlsx` : les écarts de salaire femmes / hommes, par métier + niveau.

Le tableau de bord arrive dans `output/dashboard/`, sous un nom qui porte la date et l'heure du lancement, par exemple `dashboard_anomalies_2026-10-02_14-35-08.html`. Chaque lancement ajoute un fichier sans effacer les précédents ; le plus récent est le dernier de la liste. Il s'ouvre avec un navigateur (double-clic).

Le dossier `output/` n'est pas envoyé sur GitHub non plus : chaque lancement refait les résultats.

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
| 8 | `python src/anomaly_ecarts_hommes_femmes.py` | écarts femmes / hommes par métier + niveau | `output/ecarts_hommes_femmes/gender_gap.xlsx` |
| 9 | `python src/generate_dashboard_html.py` | tableau de bord | `output/dashboard/dashboard_anomalies_<date>_<heure>.html` |

Les seuils des règles, les poids et les priorités se règlent dans `config/rules.yaml`. Après une modification, relancer la commande.

## 5. En dehors du programme principal

| Commande | Ce qu'elle fait |
| --- | --- |
| `python src/anomaly_signal_regression.py` | entraîne le modèle de régression sur 80 % des salariés, le vérifie sur les 20 % restants, l'enregistre dans `models/` et affiche le salaire prédit du premier salarié du fichier, avec sa fourchette. |
| double-clic sur `lancer_notebook.bat` | ouvre [`notebooks/EDA_Positionnement_Salarial_Comite.ipynb`](notebooks/EDA_Positionnement_Salarial_Comite.ipynb) (l'analyse du positionnement salarial et le choix des variables de la régression, pour le comité) dans le navigateur. Il crée le `.venv` s'il manque, ou le refait s'il a été copié depuis un autre PC, installe `requirements-notebook.txt`, puis ouvre le notebook déjà branché sur le Python du `.venv` (le kernel « Python (.venv salaires) ») : il n'y a rien à choisir, et pas besoin de l'extension Jupyter de VS Code. Garder la fenêtre noire ouverte pendant qu'on s'en sert ; la fermer arrête le notebook. Les graphes sont interactifs (zoom, infos du salarié au survol de la souris) : ils s'affichent quand on lance tout le notebook (menu « Run », puis « Run All Cells »). |
| double-clic sur `fiabilisation_diplomes/lancer_notebook.bat` | ouvre [`fiabilisation_diplomes/Fiabilisation_Diplomes_pas_a_pas_v12.ipynb`](fiabilisation_diplomes/Fiabilisation_Diplomes_pas_a_pas_v12.ipynb) (la fiabilisation de l'extraction des diplômes, étape par étape : niveau, libellé du diplôme, école, doublons, contrôles, puis une ligne par salarié) dans le navigateur, exactement comme le notebook du comité : il passe par le `lancer_notebook.bat` du projet, avec le même `.venv` et le même kernel. Le notebook lit l'extraction posée à côté de lui, dans `fiabilisation_diplomes/`, et y écrit son résultat, `BDD_Diplomes_FINAL.xlsx`. Pour une nouvelle extraction : déposer le fichier Excel dans ce dossier, changer `FICHIER_SOURCE` dans la deuxième cellule, puis menu « Run », « Run All Cells ». |
| double-clic sur `visualisation/exploration_salaires.html` | ouvre dans Edge ou Chrome la page d'exploration des données salariales, sans Python ni internet : elle refait les calculs du notebook du comité et montre 11 graphes (masse salariale, grille, marché, ancienneté, compétences, 9-Box, équité), avec des filtres et un bouton « Agrandir ». À chaque ouverture, la page attend les trois fichiers : les glisser dans le cadre « Déposer les trois fichiers ici », ou cliquer sur « Choisir les fichiers » (Ctrl + clic pour en prendre plusieurs). Elle ne lit aucun fichier toute seule, ne garde rien d'une ouverture à l'autre et ne demande aucune autorisation au navigateur. Pour mettre la page à jour, déposer le nouveau fichier : il remplace celui du même nom. On peut ranger les fichiers dans `visualisation/donnees/` (à créer), qui n'est pas envoyé sur GitHub. |
| `python -m decision_support.app` | ouvre l'aide à la décision sur **http://127.0.0.1:8765** (arrêter avec `Ctrl+C`) ; mode d'emploi dans [`decision_support/README.md`](decision_support/README.md). |
| `python src/generate_sources.py` | fabrique de nouvelles données fictives, sans anomalie. **Attention :** il réécrit les trois fichiers de `input/` et remplace donc les vôtres. |
| `python src/generate_sources_anomalies.py` | fabrique les mêmes données fictives, puis y ajoute des anomalies volontaires (400 salaires hors grille ou très bas, 10 matricules en double), pour que la détection ait de vraies anomalies à trouver. **Même attention** que pour la ligne précédente. |

<!--
Modèle à recopier à la fin du fichier pour chaque nouvel envoi.
Avant d'envoyer, « git log --oneline origin/main..HEAD » liste les commits qui vont partir.

## JJ/MM/AAAA — Titre court de l'envoi

Une phrase : ce que cet envoi apporte.

| Commit | Titre | En bref |
|---|---|---|
| [`abc1234`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/abc1234) | feat: ... | ... |
-->
