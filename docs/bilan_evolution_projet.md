# Détection des anomalies salariales — Bilan du projet

**Du fichier `archive/detect_salary_anomalies_custom.txt` à la version actuelle dans `src/`.**

## 1. Notre objectif

Repérer les salaires à examiner. Expliquer les alertes. Aider les RH à fixer les priorités.

Le code initial comparait déjà les salaires aux grilles internes, au marché et aux collègues. Il utilisait aussi un modèle de détection automatique. Nous avons conservé cette base et corrigé ses points faibles.

## 2. Ce que nous avons supprimé

- **Le renommage automatique des colonnes.** Les fichiers doivent utiliser les noms attendus. Cela évite les correspondances ambiguës. Dans le fichier initial, les dictionnaires étaient déjà désactivés, mais encore référencés.
- **Le nettoyage automatique des montants.** Il pouvait modifier un nombre correct en supprimant son point décimal. Les montants doivent maintenant être préparés. Une valeur illisible est signalée et traitée comme manquante.
- **La colonne Pays dans le traitement.** Le périmètre prévu concerne un seul pays. Les comparaisons reposent sur le métier et le grade. La ville n’intervient pas dans les calculs.
- **L’ancienne fonction de comparaison entre collègues.** Elle n’était pas appelée. Nous avons gardé la fonction réellement utilisée.
- **Le score `Cohort_ZScore` et le double calcul de l’effectif.** Ils faisaient doublon avec les indicateurs conservés. `PeerZ` reste le score utilisé pour comparer les collègues.
- **L’ancienne fonction de formatage.** Elle n’était plus utilisée. Le formatage à deux décimales est conservé.
- **Les réglages `admin` et `grade_inversion`.** Aucun contrôle correspondant n’était implémenté. Leur présence donnait une fausse impression de couverture.

## 3. Ce que nous avons changé

Les extraits viennent du code actuel. La mention **« Relecture »** indique les corrections ajoutées pendant cette vérification.

### Des salariés comptés une seule fois

Une grille dupliquée pouvait multiplier les lignes d’un salarié. Nous conservons la première correspondance et signalons le doublon.

Dans `anomaly_core.py` — `compute_features` :

```python
bands_ref = bands_ref.drop_duplicates(subset=ref_cols, keep="first")
```

Les matricules en double dans le fichier employés restent signalés, mais conservés. Ils demandent une vérification de la source.

### Un classement sans trous

Un score de 69,4 pouvait tomber en `Info`. Il est maintenant classé `Major`. Le classement utilise les seuils de départ, du plus élevé au plus faible.

Dans `anomaly_core.py` — `aggregate_risk` :

```python
for name, (lo, _hi) in categories_par_severite_decroissante:
    if x >= lo:
        return name
```

### Des données manquantes correctement traitées

Les montants illisibles deviennent manquants. Les divisions par zéro sont protégées. Une grille sans colonnes obligatoires provoque une erreur claire.

**Relecture :** une ancienneté vide était classée « plus de 20 ans ». Elle reste maintenant inconnue. Les valeurs négatives ou infinies suivent la même règle.

Dans `anomaly_core.py` — `bucket_anciennete` :

```python
if not np.isfinite(val) or val < 0:
    return "NA"
```

Le calcul entre collègues conserve les écarts dans les groupes presque homogènes. **Relecture :** un salaire manquant ne reçoit plus un faux score nul dans un groupe constant.

### Une IA qui ne signale pas tout le monde à tort

Les variables sont préparées avant le calcul. Les colonnes vides sont écartées. Les réglages du modèle sont lus dans le YAML.

**Relecture :** les champs RH absents ne bloquent plus le modèle. Sans donnée exploitable, le score reste indisponible. Des scores tous identiques ne déclenchent plus une alerte générale.

Dans `anomaly_core.py` — `apply_ml_strong_signal` :

```python
if df["ML_AnomalyScore"].nunique() < 2:
    return df
```

### Des recommandations cohérentes avec les réglages

Le nouveau YAML correspond aux paramètres réellement lus. Les paramètres manquants sont signalés.

**Relecture :** les recommandations utilisaient encore des seuils fixes. Elles lisent désormais les mêmes seuils que la détection. Les deux scripts transmettent ces réglages.

Dans `anomaly_core.py` — `recommendations` :

```python
compa_lo = float(rule_params.get("compa_ratio_low", 0.85))
compa_hi = float(rule_params.get("compa_ratio_high", 1.15))
```

### Des restitutions fidèles aux chiffres

Excel reçoit les valeurs numériques. Le CSV utilise une copie formatée. Les totaux ne dépendent plus de la présentation des montants. Le graphique affiche les quatre priorités.

Dans `detect_salary_anomalies_custom_fixed.py` :

```python
out_csv = format_numeric_fields(out_numeric.copy())
```

**Relecture :** Excel trie les dossiers par score décroissant. Le total distingue les salariés analysés des anomalies. Le tableau de bord affiche « unité source », sans prétendre convertir les montants en milliers de MAD. Les libellés sont affichés comme du texte, même s’ils contiennent des caractères HTML.

### Une régression mieux protégée

**Relecture :** les salaires nuls, négatifs ou infinis sont exclus du calcul logarithmique. Les salariés restent dans les résultats, sans score de régression.

Dans `anomaly_regression.py` — `_preparer_table_regression` :

```python
exploitable = np.isfinite(fixe) & (fixe > 0) & job_family.notna() & grade.notna()
```

Le rapport hommes/femmes vérifie aussi les catégories comparées. Il ne présente plus une comparaison avec « Autre » comme un écart hommes/femmes.

## 4. Ce que nous avons ajouté ou réorganisé

**Un code séparé par rôle.** Le lancement, les calculs et les exports sont dans des fichiers distincts. Cela facilite les corrections. Les motifs et recommandations sont aussi calculés par colonnes pour limiter les boucles.

**Un signal pour les profils très atypiques.** Un score IA élevé peut maintenant faire remonter un dossier sans alerte de règle. Ce changement peut modifier sa priorité.

**Un tableau de bord HTML.** Il présente les résultats et permet de retrouver les salariés concernés depuis les graphiques.

**Une variante avec régression.** Elle compare le salaire observé au salaire estimé selon le profil. Elle reste séparée du moteur principal. Ses pondérations sont différentes et peuvent changer le classement.

**Une expérimentation de plusieurs modèles.** Le notebook compare trois détecteurs et étudie leur accord. Cette expérimentation n’est pas intégrée au moteur principal.

**Des tests automatiques.** Ils vérifient les calculs et protègent les corrections contre de futures erreurs.

**Une aide à la décision dans `decision_support/`.** Une interface locale permet de vérifier un salaire ou d'obtenir une fourchette indicative. Elle utilise la grille exacte du métier et du grade, puis le marché et les collègues comparables. Chaque cible proposée est revérifiée. Les références incompatibles ou insuffisantes sont signalées. Les montants sont en kMAD par an.

## 5. Où nous en sommes

La relecture et la nouvelle brique sont couvertes par **139 tests réussis**. Les deux scripts historiques ont été rejoués sur les **10 000 lignes**, avec leurs exports CSV, Excel et HTML. L'aide à la décision a été vérifiée sur les **91 couples métier/grade**.

Le moteur principal classe toujours 11 dossiers en `Critical`, 33 en `Major`, 4 238 en `Minor` et 5 718 en `Info`. Les corrections de cette relecture ne changent pas ces effectifs sur le jeu présent. Ce sont des priorités de revue, pas des erreurs de salaire confirmées.

Le point d’entrée principal est **`src/detect_salary_anomalies_custom_fixed.py`**. La régression et le notebook restent deux approches complémentaires.

## 6. Ce qui reste à valider

- Valider la méthode de proposition avec les RH. L'unité a été confirmée : milliers de MAD par an.
- Faire vérifier les alertes par les RH et ajuster les seuils.
- Tester avec un marché distinct de la grille interne. Ils sont identiques dans le jeu examiné.
- Renforcer les contrôles des fichiers et des paramètres invalides.
- Définir la pondération à utiliser lorsque la régression est indisponible. Actuellement, sa contribution vaut zéro.
- Compléter les explications individuelles de la régression.

**Le socle technique est en place. La prochaine étape est la validation métier des résultats.**
