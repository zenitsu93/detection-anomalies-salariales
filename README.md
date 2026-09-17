# Détection des anomalies salariales

Historique pédagogique reconstruit à partir du code initial, des sources finales et du bilan conservé. Les commits sont créés à la date de reconstruction ; ils ne constituent pas un journal daté du développement original.

Le fichier `archive/detect_salary_anomalies_custom.txt` est conservé sans modification. Cette première archive contient des références à des dictionnaires désactivés et ne constitue pas encore une version exécutable validée.

## Première version finalisée

Installer `requirements-dev.txt`, puis lancer :

```shell
python src/detect_salary_anomalies_custom_fixed.py --employees input/employes.csv --bands input/bands.csv --market input/market.csv --rulebook config/rules.yaml --output output/principal/anomalies.csv --excel-output output/principal/anomalies.xlsx --gender-output output/principal/gender_gap.csv
python -m pytest tests -q
```

Les valeurs Excel restent numériques ; le CSV est formaté pour la lecture. Les données sources sont synthétiques.
