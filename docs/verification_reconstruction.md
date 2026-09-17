# Vérification de la reconstruction

Contrôles exécutés sur la copie destinée à GitHub.

- Identique octet pour octet : `archive/detect_salary_anomalies_custom.txt`.
- Identique octet pour octet : `input/employes.csv`.
- Identique octet pour octet : `input/bands.csv`.
- Identique octet pour octet : `input/market.csv`.
- Identique octet pour octet : `notebooks/anomaly_classification.ipynb`.
- Le code Python final correspond au projet source (hors commentaires et documentation des modules).
- `premier-moteur` : traitement des 10 000 lignes, exports CSV/Excel/écarts de genre ; priorités {'Info': 5718, 'Minor': 4238, 'Major': 33, 'Critical': 11}.
- `principal` : traitement des 10 000 lignes, exports CSV/Excel/écarts de genre ; priorités {'Info': 5718, 'Minor': 4238, 'Major': 33, 'Critical': 11}.
- `regression` : traitement des 10 000 lignes, exports CSV/Excel/écarts de genre ; priorités {'Info': 7001, 'Minor': 2986, 'Critical': 9, 'Major': 4}.
- Les deux tableaux de bord HTML finaux ont été générés.
- Aide à la décision : 91 couples métier/grade examinés ; les cibles disponibles repassent sans alerte leur évaluation.

Les suites de tests ont été exécutées à chaque commit disposant de tests pendant la reconstruction initiale. Lors de l’audit de lisibilité, les nouvelles étapes de déplacement et d’extraction ont chacune passé 75 tests, la copie préparant la régression a passé 93 tests, et la version finale a de nouveau passé 139 tests. La mise en forme YAML a été vérifiée par égalité des paramètres ; les cellules du notebook ont été contrôlées séparément de leurs sorties enregistrées. Le notebook fourni est conservé avec ses sorties historiques ; son entraînement n’a pas été relancé.
