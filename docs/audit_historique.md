# Audit complet de la lisibilité de l’historique

Tous les commits ont été examinés, en particulier les fichiers ajoutés, les copies, les déplacements et les modifications masquées par le formatage ou les résultats enregistrés.

## Corrections

| Point | Étape | Vérification |
|---|---|---|
| Mise en forme YAML | [b35ab08](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b35ab089c7b80af2ec2a0356692d3b513c3e5c25) | Valeurs identiques ; ajout du signal fort isolé au commit suivant. |
| Déplacement du moteur | [89e2047](https://github.com/zenitsu93/detection-anomalies-salariales/commit/89e2047440d9d321dec9a51c9f9036786ef976be) | Renommage R100 détecté : contenu strictement identique. |
| Extraction des exports | [277b733](https://github.com/zenitsu93/detection-anomalies-salariales/commit/277b7336e71cfbecd9cef4eea8ef27ea2abea9cd) | Déplacement séparé des changements de calcul et des corrections Excel suivantes. |
| Notebook | [2700805](https://github.com/zenitsu93/detection-anomalies-salariales/commit/270080581836dd43397ae951e83e68e3c4f74347) | Ajouts de code séparés des résultats historiques ; notebook final inchangé. |
| Variante de régression | [4fce3be](https://github.com/zenitsu93/detection-anomalies-salariales/commit/4fce3bece644545160693157870c7017895789c3) | Copies exactes du lanceur et du YAML ; les ajouts de régression deviennent des modifications ligne par ligne. |

## Ajouts conservés comme tels

- Générateur, CSV synthétiques et tests : premiers ajouts réels.
- Premier YAML disponible : ancienne version complète absente, aucune version antérieure inventée.
- Module statistique de régression, tableau de bord et aide à la décision : nouvelles fonctionnalités ; leurs ajouts initiaux restent normalement en vert.
- Extraction des exports : fonctions déplacées, décrites dans un commit dédié avant toute correction.
- Débogage des cohortes : nouvel utilitaire de diagnostic, distinct de la fonction de production.
- Documentation et dépendances : nouveaux fichiers explicites.

Le code final, les données, le notebook et les configurations restent identiques à la version publiée avant cet audit. Seule la documentation finale change. Une sauvegarde de l’ancien historique est conservée dans une branche locale.
