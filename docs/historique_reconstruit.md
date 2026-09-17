# Historique reconstruit du projet

## Lire les différences

Le premier commit contient l’archive `.txt` intacte et sa copie Python initiale. Le deuxième modifie cette copie : les suppressions et ajouts apparaissent dans le même fichier. Consulter l’historique du Python plutôt que celui de l’archive.

Le déplacement du moteur vers `anomaly_core.py`, l’extraction des exports, la vectorisation et la copie préparant la régression sont des étapes séparées. Le YAML distingue mise en forme et paramètres. Les analyses du notebook sont séparées de leurs sorties enregistrées.

Git suit les renommages de fichiers entiers ; il ne maintient pas automatiquement une filiation séparée pour chaque fonction extraite vers plusieurs modules. Le commit d’extraction indique donc explicitement les fonctions transférées vers `anomaly_io.py`. Un module réellement nouveau reste normalement affiché en vert lors de son introduction.

## Méthode

Historique pédagogique reconstruit depuis l’archive, les sources finales et le bilan. Les dates sont celles de la reconstruction, pas des dates historiques inventées. Le générateur suit la deuxième étape ; le notebook suit la première version finalisée du moteur. La première restitution HTML est une reconstruction minimale, aucune ancienne maquette n’étant conservée. L’ancien YAML antérieur aux sources disponibles n’a pas été inventé.

Les données et le code final sont conservés. Les sorties du notebook proviennent du fichier fourni. Les protections des exports et de la régression sont introduites avec ces briques puis couvertes par leurs tests de relecture.

[Audit des différences](audit_historique.md) · [Vérification fonctionnelle](verification_reconstruction.md).

## Parcours chronologique

1. **chore: conserver le code initial de détection salariale** — [3a0f243](https://github.com/zenitsu93/detection-anomalies-salariales/commit/3a0f24345ca94d1619cc9b41f1c23408eb656018)

   Conserver la référence originale et expliquer la reconstruction. Exclure les environnements et sorties régénérables ; les CSV synthétiques seront versionnés.

2. **fix: simplifier la préparation des données salariales** — [4522272](https://github.com/zenitsu93/detection-anomalies-salariales/commit/452227240c0c71c1512e6dedafbde6957b37c4d9)

   Retirer le renommage désactivé et la dimension Pays. Remplacer le nettoyage qui supprimait les points décimaux par une conversion numérique explicite.

3. **feat: ajouter le générateur et les données salariales synthétiques** — [b1ea3d6](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b1ea3d6346a276e8206e4b95a26fe0dbb2ef9dee)

   Placer la génération juste après les premières corrections. Conserver les trois CSV fournis et documenter les unités ainsi que le remplacement des fichiers lors de la génération.

4. **fix: sécuriser les jointures et les ratios salariaux** — [856c056](https://github.com/zenitsu93/detection-anomalies-salariales/commit/856c0562a25d8a4b72e14715a2a70944a7d15dce)

   Vérifier les colonnes, dédupliquer les références et protéger les divisions par zéro. Les tests couvrent les grilles absentes, les doublons et les montants illisibles.

5. **refactor: retirer les anciennes fonctions inutilisées** — [80a8bf2](https://github.com/zenitsu93/detection-anomalies-salariales/commit/80a8bf21256539219e263cb97c9e64be02d62693)

   Supprimer la fonction de cohortes non appelée et l’ancien formatage. Le calcul actif des cohortes sera fiabilisé dans son propre commit.

6. **fix: aligner le fichier de règles sur le moteur** — [8bdb140](https://github.com/zenitsu93/detection-anomalies-salariales/commit/8bdb14007ffbbd83b97f1e9624daca5fc1c1d6de)

   Utiliser les clés réellement lues pour les poids, seuils et cohortes. Signaler les paramètres absents au lieu de les remplacer silencieusement.

7. **fix: fiabiliser les écarts entre collègues** — [8eeac3f](https://github.com/zenitsu93/detection-anomalies-salariales/commit/8eeac3fa3a334aeeeb9aedaf9af1fd267da82788)

   Conserver les écarts lorsque la MAD est nulle, élargir uniquement les petites cohortes et supprimer les indicateurs redondants. Ajouter un jeu de débogage ciblé.

8. **fix: préparer et configurer Isolation Forest** — [6e0e8b3](https://github.com/zenitsu93/detection-anomalies-salariales/commit/6e0e8b32b88eb29d67afe4213bdd121e7a9f0bbb)

   Convertir et imputer les variables, écarter les colonnes vides et lire le nombre d’arbres et la contamination dans le YAML. Borner le score normalisé entre 0 et 100.

9. **style: documenter et harmoniser le fichier de règles** — [b35ab08](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b35ab089c7b80af2ec2a0356692d3b513c3e5c25)

   Harmoniser uniquement les commentaires et la présentation du YAML. Le prochain commit montrera séparément les paramètres du signal IA fort.

10. **feat: faire remonter les profils au signal IA élevé** — [3417496](https://github.com/zenitsu93/detection-anomalies-salariales/commit/3417496cfdf3222209a43f4babac506ca06225c8)

   Ajouter le signal fort aux profils sans alerte de règle, avec percentile et poids configurables. Ne pas compter deux fois un profil déjà signalé.

11. **fix: classer les scores décimaux sans trous entre priorités** — [b7aa0ae](https://github.com/zenitsu93/detection-anomalies-salariales/commit/b7aa0aef08d2fb53c4fabb23fc902b0ee97dc022)

   Parcourir les seuils inférieurs par sévérité décroissante : 69,4 reste Major. Couvrir les frontières et les pondérations personnalisées.

12. **refactor: déplacer le script vers le module de calcul** — [89e2047](https://github.com/zenitsu93/detection-anomalies-salariales/commit/89e2047440d9d321dec9a51c9f9036786ef976be)

   Déplacer le script sans changer son contenu. À cette étape intermédiaire, lancer python src/anomaly_core.py ; le lanceur habituel est rétabli au commit suivant. Adapter uniquement les imports des tests.

13. **refactor: extraire les exports et rétablir le lanceur** — [277b733](https://github.com/zenitsu93/detection-anomalies-salariales/commit/277b7336e71cfbecd9cef4eea8ef27ea2abea9cd)

   Extraire les fonctions existantes dans anomaly_io.py et rétablir le point d’entrée. Le module d’exports est nouveau mais ses fonctions sont déplacées sans correction métier ; read_csv_guess_sep reprend _read_csv_guess_sep.

14. **refactor: vectoriser les motifs et les recommandations** — [c3253d9](https://github.com/zenitsu93/detection-anomalies-salariales/commit/c3253d931e51b0293b0754db9954b3a955f79b06)

   Modifier les fonctions déjà présentes dans anomaly_core.py : remplacer les parcours ligne par ligne par des calculs par colonnes. Les déplacements de fichiers sont isolés dans les deux commits précédents.

15. **fix: finaliser les exports numériques et la synthèse Excel** — [82754b6](https://github.com/zenitsu93/detection-anomalies-salariales/commit/82754b681dd0a4724f83573d8b64839fc79de72d)

   Séparer la copie CSV des valeurs Excel, corriger les totaux et représenter les quatre priorités. Finaliser le traitement principal avant l’expérimentation notebook.

16. **feat: comparer trois détecteurs dans un notebook** — [c18d1bd](https://github.com/zenitsu93/detection-anomalies-salariales/commit/c18d1bd4e752e08b071129ea2739802ddb535a98)

   Après la première version finalisée, ajouter l’exploration et les modèles Isolation Forest, LOF et One-Class SVM. Réutiliser les indicateurs du moteur sans reprendre son verdict.

17. **feat: analyser le consensus et expliquer les modèles** — [d5226af](https://github.com/zenitsu93/detection-anomalies-salariales/commit/d5226af244452e8336b1dadf97a6cb0677cb9949)

   Compléter le notebook avec les accords entre détecteurs, les visualisations, le modèle explicatif et la sauvegarde. Les sorties historiques seront ajoutées séparément.

18. **docs: conserver les résultats enregistrés du notebook** — [2700805](https://github.com/zenitsu93/detection-anomalies-salariales/commit/270080581836dd43397ae951e83e68e3c4f74347)

   Ajouter uniquement les sorties et compteurs d’exécution du notebook fourni, sans les présenter comme un nouvel entraînement. Les cellules de code et de texte sont identiques au commit précédent.

19. **feat: générer une première restitution HTML autonome** — [6a6c2b0](https://github.com/zenitsu93/detection-anomalies-salariales/commit/6a6c2b070ef42822977a61e3dac866bf75562638)

   Ajouter les agrégations, indicateurs, tables et graphiques de synthèse à partir des exports CSV. Cette étape est une reconstruction minimale de la restitution, pas une ancienne maquette conservée.

20. **feat: enrichir les graphiques et consulter les salariés concernés** — [35e98d2](https://github.com/zenitsu93/detection-anomalies-salariales/commit/35e98d217fe0fbdb28d3a0da04ca14de48d9d3df)

   Introduire la présentation complète, les graphiques spécialisés et le panneau de détail au clic. Les libellés sont échappés dès cette version reconstruite.

21. **feat: intégrer le tableau de bord au traitement principal** — [a2faf7f](https://github.com/zenitsu93/detection-anomalies-salariales/commit/a2faf7f7048fbb1c260c04abb80a9e328aa0d535)

   Générer le HTML depuis les données en mémoire. Ajouter --html-output et --no-html, ainsi que les dossiers de sortie automatiques.

22. **feat: estimer le salaire attendu par régression** — [846fb31](https://github.com/zenitsu93/detection-anomalies-salariales/commit/846fb319ed58691d0f8bbda0454eea9db0682ea3)

   Ajouter la régression OLS, les catégories rares, les contrôles d’effectif et le score des résidus. Les protections sur les salaires invalides sont incluses dès l’introduction de cette brique.

23. **refactor: préparer la variante de régression par copie du moteur** — [4fce3be](https://github.com/zenitsu93/detection-anomalies-salariales/commit/4fce3bece644545160693157870c7017895789c3)

   Copier sans changement le lanceur principal et son YAML vers les fichiers de la variante. À ce stade cette copie fonctionne encore à deux signaux ; le prochain commit affiche les changements ajoutant la régression.

24. **feat: combiner règles IA et régression dans une variante dédiée** — [ff27194](https://github.com/zenitsu93/detection-anomalies-salariales/commit/ff27194e217c13ef9aefacda071dc465e23ef558)

   Ajouter le point d’entrée indépendant, les poids 0,60/0,25/0,15 et les colonnes de régression. Préserver le moteur principal à deux signaux.

25. **feat: produire le rapport femmes-hommes ajusté** — [e840c3c](https://github.com/zenitsu93/detection-anomalies-salariales/commit/e840c3cbb36971c3e9670fad3732a6dac8b44fdf)

   Extraire le coefficient M/F, son intervalle de confiance et sa significativité. Ajouter --reg-gender-output et distinguer ce rapport des médianes brutes.

26. **fix: gérer les profils incomplets et les scores IA constants** — [f815103](https://github.com/zenitsu93/detection-anomalies-salariales/commit/f81510356f4ac2d9e58608bb2a43cdc1ddf42e07)

   Laisser inconnue une ancienneté invalide et un salaire absent sans score. Accepter les champs RH absents et éviter une alerte générale pour des scores identiques.

27. **fix: aligner les recommandations sur les seuils configurés** — [36d1f18](https://github.com/zenitsu93/detection-anomalies-salariales/commit/36d1f181154c9ce93846de083c94903532f15a71)

   Lire les mêmes bornes CompaRatio que la détection et transmettre les paramètres depuis les deux scripts. Tester des seuils personnalisés.

28. **test: protéger les restitutions Excel et HTML** — [cfd6a02](https://github.com/zenitsu93/detection-anomalies-salariales/commit/cfd6a02e6a15c3ab76fdacfd26a7f8b41ea0a7a9)

   Couvrir les types numériques, totaux, ordre des priorités, unités et échappement HTML. Ces corrections étant intégrées lors de l’introduction des exports, ce commit ajoute leur couverture dédiée sans recréer artificiellement les défauts.

29. **test: couvrir les cas limites de la régression et du rapport de genre** — [d78177f](https://github.com/zenitsu93/detection-anomalies-salariales/commit/d78177fba581fad9850c524ae7ae3ed66876e240)

   Vérifier les salaires nuls, négatifs ou infinis et les catégories de sexe rares ou supplémentaires. Les garde-fous sont déjà présents dans la brique de régression introduite plus haut.

30. **feat: évaluer un salaire à partir des références du projet** — [60576ff](https://github.com/zenitsu93/detection-anomalies-salariales/commit/60576ff287c887d7c54b62f6673595875c50e620)

   Ajouter le moteur de comparaison métier/grade, les pairs et les contrôles explicites. Exclure le salarié de ses références et identifier les fichiers utilisés.

31. **feat: proposer une fourchette et une cible salariale vérifiée** — [d07d275](https://github.com/zenitsu93/detection-anomalies-salariales/commit/d07d275cb01d1c7aefb9039ed8d90bd76044bab1)

   Croiser grille, CompaRatio, marché et pairs ; arrondir les bornes vers l’intérieur et revérifier la cible. Signaler les références incompatibles sans inventer de montant.

32. **feat: ajouter l’interface locale d’aide à la décision** — [ea5950c](https://github.com/zenitsu93/detection-anomalies-salariales/commit/ea5950c1a2e22536f8cd83747e241f7435d1becf)

   Exposer les modes évaluation et proposition dans une interface locale. Valider les saisies, afficher les explications et permettre le téléchargement du compte rendu JSON. Couvrir moteur et API.

33. **docs: finaliser le dépôt et documenter la reconstruction**

   Organisation finale, bilan, audit de lisibilité et vérifications.
