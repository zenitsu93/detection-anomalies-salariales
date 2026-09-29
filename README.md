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

<!--
Modèle à recopier à la fin du fichier pour chaque nouvel envoi.
Avant d'envoyer, « git log --oneline origin/main..HEAD » liste les commits qui vont partir.

## JJ/MM/AAAA — Titre court de l'envoi

Une phrase : ce que cet envoi apporte.

| Commit | Titre | En bref |
|---|---|---|
| [`abc1234`](https://github.com/zenitsu93/detection-anomalies-salariales/commit/abc1234) | feat: ... | ... |
-->
