# Aide à la décision salariale

Deux modes : **vérifier un salaire** et **obtenir une proposition**.

## Démarrer

Depuis la racine du projet, dans PowerShell :

```powershell
.\.venv\Scripts\python.exe -m decision_support.app
```

Ouvrir **http://127.0.0.1:8765**. Arrêter avec `Ctrl+C`.
Si le port est occupé, ajouter `--port 8766`. Aucune dépendance supplémentaire n'est nécessaire.

## Utilisation

1. Choisir le mode, le métier et le grade.
2. Renseigner l'ancienneté si une comparaison plus fine est souhaitée.
3. Pour vérifier un salaire, saisir le montant annuel en **kMAD** : 200 signifie 200 000 MAD.
4. Pour un salarié existant, saisir son matricule afin de l'exclure des pairs.
5. Consulter les comparaisons et, si disponible, la fourchette et la cible indicative.

Le bouton de téléchargement enregistre un compte rendu JSON dans le navigateur. Aucun profil saisi n'est enregistré sur le serveur. Les fichiers d'entrée ne sont pas modifiés.

## Références utilisées

- `input/bands.csv` : ligne exacte **métier + grade**. Les grilles de métiers différents ne sont jamais mélangées.
- `input/market.csv` : médiane du même métier et grade. Le fichier peut être absent.
- `input/employes.csv` : pairs du même métier et grade, puis de la même tranche d'ancienneté si l'effectif suffit.
- `config/rules.yaml` : seuils CompaRatio, marché, écart entre pairs et effectif minimal.
- `decision_support/settings.yaml` : libellé de l'unité, confirmé en **kMAD par an**.

Les sources sont chargées au démarrage. **Redémarrer après une modification.** Le compte rendu contient les empreintes des fichiers pour identifier les références utilisées.

L'âge, le sexe, les compétences, le 9Box et Hot job ne déterminent pas le montant dans cette première version. Aucun coefficient supplémentaire n'est inventé. L'ancienneté affine la comparaison, sans majoration automatique.

## Méthode de proposition

La fourchette est l'intersection de la bande interne, de l'intervalle autorisé par le CompaRatio, des tolérances du marché et, si l'effectif suffit, des quartiles P25–P75 des pairs. Elle reste aussi en deçà du seuil d'alerte entre pairs. La cible est leur médiane, ramenée dans cette fourchette. Sans pairs suffisants, le milieu de grille sert de cible et la référence est signalée comme incomplète.

Les bornes sont arrondies vers l'intérieur à deux décimales. La cible est revérifiée par le mode évaluation. Les seules différences d'arrondi informatique aux seuils sont neutralisées.

Une grille absente, invalide ou contradictoire empêche la proposition. Des intervalles incompatibles donnent un message d'arbitrage, sans montant inventé. Les doublons de matricule sont exclus des statistiques. Un matricule inconnu est rejeté.

Le mode évaluation reprend les seuils du moteur existant. Il vérifie aussi **strictement** Min et Max, sans la tolérance hors bande du traitement par lot. Le salaire envisagé n'est jamais ajouté aux références. L'écart entre pairs utilise la même convention médiane/MAD puis moyenne/écart-type que le moteur, mais estimée sur les références seules.

La moitié centrale des pairs sert à construire une proposition. Être en dehors de cette moitié ne déclenche pas à lui seul une alerte : l'évaluation utilise le seuil d'écart entre pairs.

## Portée de cette version

Cette version utilise des comparaisons explicites. Elle ne réentraîne ni l'Isolation Forest ni la régression pour chaque saisie. Le score du traitement par lot n'est pas repris comme une autorisation salariale.

La proposition est un **repère de discussion à valider**, pas un salaire optimal démontré. Dans le jeu actuel, le marché et le milieu de grille sont identiques ; l'interface le signale. Les données du projet doivent être confirmées comme références métier avant un usage opérationnel.

L'application écoute uniquement sur l'ordinateur local. Elle n'est pas un service multi-utilisateur déployé.

## Vérifier

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_support.py -q
```
