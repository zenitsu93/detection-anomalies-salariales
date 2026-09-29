# Chronologie du projet

Le projet repart du code d'origine et le réécrit fichier par fichier.

| Commit      | Titre                                                         | En bref                                                                                                                                                           |
| ----------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `c75df63` | docs: ajouter la chronologie des commits | `README.md` : ce tableau, affiché sur la page d'accueil, qui suit les commits du plus ancien au plus récent. |
| `640a545` | chore: enregistrer le code d'origine, sans correction         | Le code d'origine, gardé tel quel dans `archive/`.                                                                                                              |
| `1da24e1` | feat: préparer le tableau des salariés (prétraitement)     | `src/anomaly_pretraitement.py` : lit les trois fichiers d'entrée, retire les doublons, ajoute la fourchette de la grille, le salaire du marché et les ratios. |
| `8bdea95` | feat: ajouter le générateur de données salariales fictives | `src/generate_sources.py` et les trois fichiers de `input/` : 10 000 salariés.                                                                               |

<!--
Modèle à recopier à la fin du fichier pour chaque nouvel envoi.
Avant d'envoyer, « git log --oneline origin/main..HEAD » liste les commits qui vont partir.

## JJ/MM/AAAA — Titre court de l'envoi

Une phrase : ce que cet envoi apporte.

| Commit | Titre | En bref |
|---|---|---|
| `abc1234` | feat: ... | ... |
-->
