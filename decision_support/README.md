# Aide à la décision salariale

Pour un métier, un niveau et un profil, l'application donne **le salaire prédit par le modèle** et la fourchette où le vrai salaire tombe 9 fois sur 10, placés dans la grille du poste.

Depuis le 17/11/2026, c'est son seul résultat : la fourchette et la cible tirées des règles ont été retirées, car elles faisaient un deuxième résultat à côté du salaire prédit, et la page montrait trop de chiffres. Le mode « vérifier un salaire » et le champ Matricule avaient été retirés le 09/11/2026.

![Aperçu de l'application : le salaire prédit, et sa place dans la grille du poste](static/apercu.png)

## Démarrer

Depuis la racine du projet, dans PowerShell :

```powershell
.\.venv\Scripts\python.exe -m decision_support.app
```

Ouvrir **http://127.0.0.1:8765**. Arrêter avec `Ctrl+C`.
Si le port est occupé, ajouter `--port 8766`. Aucune dépendance supplémentaire n'est nécessaire.

## Utilisation

1. Choisir le métier et le niveau (ceux du nouveau poste, pour une promotion).
2. Remplir le profil de la personne : ancienneté, niveau d'études, âge, compétence N-1, performance N-1 et Hot job. C'est ce que lit le modèle, avec les valeurs du fichier des salariés : un choix dans une liste, ou un nombre entre le plus petit et le plus grand du fichier. Tous les champs sont obligatoires : sans l'un d'eux, le modèle ne peut pas prédire.
3. Lire le salaire prédit.

## Lire le résultat

- **Le salaire prédit**, en grand, et dessous sa fourchette : 9 fois sur 10, le vrai salaire d'un tel profil tombe entre ces deux montants.
- **Dans la grille du poste** : une seule ligne. La barre grise est la grille, du Min au Max. Le point est le salaire prédit, et la barre dorée autour de lui est sa fourchette. On voit d'un coup d'œil si le salaire prédit est en bas, au milieu ou en haut de la grille, et si sa fourchette en sort.
- **Sous la figure**, une phrase donne les deux autres repères : la médiane du marché, et la médiane des collègues comparables, avec leur nombre et le groupe retenu.

Aucun profil saisi n'est enregistré sur le serveur. Les fichiers d'entrée ne sont pas modifiés.

Les couleurs de marque sont regroupées en haut de `static/style.css` (`--brand`, `--brand-soft`, `--brand-dark`) pour être ajustées à la charte officielle.

## Références utilisées

- `input/bands.xlsx` : ligne exacte **métier + niveau**. Les grilles de métiers différents ne sont jamais mélangées.
- `input/market.xlsx` : médiane du même métier et niveau. Le fichier peut être absent.
- `input/employes.xlsx` : les collègues, choisis comme dans `src/anomaly_cohortes.py` : même niveau + même métier + même tranche d'ancienneté, sinon même niveau + même métier, sinon même niveau seul (tous métiers). Le premier groupe qui compte au moins `cohort_min_size` collègues est retenu.
- `config/rules.yaml` : l'effectif minimal d'un groupe de collègues (`cohort_min_size`) et les groupes à essayer (`cohort_widening_steps`). Les seuils des règles ne servent plus ici.
- Le modèle du salaire prédit, appris au démarrage dans `decision_support/engine.py`. Depuis le 17/11/2026, sa façon de faire est celle du modèle M5 du notebook `notebooks/Prediction_Compa_Ratio.ipynb` (du 16/11 au 17/11, c'était M6, qui apprenait le Compa-Ratio) :
  - il apprend le **salaire**, en logarithme : un écart se lit alors en pourcentage, et les très hauts salaires pèsent moins. Salaire prédit = exponentielle du log prédit ;
  - avec un **gradient boosting** : des centaines de petits arbres qui se corrigent l'un l'autre, pour suivre des effets qui ne sont pas en ligne droite ;
  - il lit les colonnes du notebook (liste `COLONNES`, en haut de `engine.py`) : le niveau, le niveau d'études (en rang), l'âge à l'embauche (âge − ancienneté), l'ancienneté, la compétence N-1, la performance N-1 (en rang), le Hot job et le ratio grille / marché. Il reçoit en plus le Mid de la grille, en logarithme : c'est par lui qu'il connaît la grille du poste. Il ne lit plus le métier, le 9Box ni la catégorie d'école, et toujours ni le sexe, ni le pôle ;
  - la fourchette « 9 fois sur 10 » garde la recette de `src/anomaly_signal_regression.py` : chaque salarié est prédit par un modèle qui ne l'a pas vu, et on garde les erreurs entre les 5 % les plus basses et les 5 % les plus hautes.

  La détection, elle, garde sa propre régression (`src/anomaly_signal_regression.py`) : le salaire prédit de cette page et le salaire attendu de la détection ne sont donc pas le même chiffre.

Les montants sont en **kMAD par an**, comme dans les fichiers d'entrée.

Les sources sont chargées au démarrage. **Redémarrer après une modification.**

Le sexe n'est jamais utilisé. Comme dans `src/anomaly_pretraitement.py`, un matricule en double, ou un métier + niveau en double dans la grille ou le marché, garde sa première ligne. Sans grille exploitable pour le métier et le niveau choisis (ou sans marché), il n'y a pas de salaire prédit : la page le dit.

## Portée de cette version

Le modèle apprend une fois, au démarrage, en quelques secondes. La page ne relance ni les règles, ni l'Isolation Forest, et ne calcule pas de score général.

Le salaire prédit est ce que le modèle attend pour un tel profil, d'après les salaires d'aujourd'hui : c'est un **repère de discussion à valider**, pas un salaire optimal démontré. Si les salaires d'aujourd'hui portent des écarts injustifiés, le modèle les a appris avec le reste. Les données du projet doivent être confirmées comme références métier avant un usage opérationnel.

L'application écoute uniquement sur l'ordinateur local. Elle n'est pas un service multi-utilisateur déployé.
