# Les réglages de la régression des salaires.
#
# Les trois notebooks du dossier lisent ce fichier : ils travaillent donc sur les mêmes salariés,
# avec les mêmes colonnes et les mêmes modèles. Un réglage se change ici, une seule fois.
#
# Après un changement : enregistrer ce fichier, puis relancer le notebook depuis sa première cellule.


# ----------------------------------------------------------------------------------------------
# 1. LES DONNÉES
# ----------------------------------------------------------------------------------------------

# Le dossier des trois fichiers Excel (employes.xlsx, bands.xlsx, market.xlsx).
# Le chemin part de ce dossier-ci : 'input' est le sous-dossier input, juste à côté de ce fichier.
# Pour d'autres données : remplacer les trois fichiers de input, ou écrire ici le chemin d'un autre dossier.
DOSSIER = 'input'


# ----------------------------------------------------------------------------------------------
# 2. LES SALARIÉS QU'ON RETIRE
# ----------------------------------------------------------------------------------------------

# Les anomalies. La détection d'anomalies donne une priorité à chaque salarié : Critical, Major, Minor ou Info.
# A_RETIRER est la liste des priorités qu'on retire avant la régression.
# [] : personne n'est retiré, la régression se fait sur tous les salariés.
# Une cinquième valeur existe : « Outlier positif », un salarié sans alerte payé au-dessus du Max de sa grille.
# Ce n'est pas une anomalie, mais ces salaires élevés dispersent les résultats : on peut les retirer aussi.
# ['Critical'] : seulement les anomalies les plus graves. Pour en retirer plus : ['Critical', 'Major', 'Outlier positif'].
A_RETIRER = ['Critical', 'Outlier positif']

# Les valeurs aberrantes (outliers). Ce n'est pas la même chose que les anomalies : un outlier est une valeur
# au-delà des moustaches de la boîte à moustaches, dans une des colonnes de COLONNES_RETRAIT.
# True : une ligne qui a un outlier est écartée. False : les outliers restent dans le tableau.
ENLEVER = False

# Les colonnes où l'on cherche des outliers. Pour en épargner une, effacer son nom.
# Le salaire, la grille et le marché n'y sont pas : un salaire élevé est celui d'un haut niveau, pas une erreur.
COLONNES_RETRAIT = ['Compa_Ratio', 'Age_Embauche', 'Competence_N1']


# ----------------------------------------------------------------------------------------------
# 3. LES COLONNES DU MODÈLE
# ----------------------------------------------------------------------------------------------

# Les colonnes que les modèles reçoivent. Un # devant une colonne la met de côté.
# Le notebook 1_Visualisations aide à les choisir (corrélations, VIF, ce que chaque colonne apporte).
COLONNES = [
    'Niveau',                  # le niveau du poste
    'Niveau_Etude_Max',        # le niveau d'études
    'Age_Embauche',            # âge − ancienneté
    'Anciennete',              # l'ancienneté, en années
    'Competence_N1',           # la note de compétence de l'an dernier
    'Performance_N1',          # la performance de l'an dernier
    'Hot_job',                 # la tension du métier sur le marché
    'Ratio_Grille_Marche',     # Mid / médiane du marché
]

# L'ancienneté en buckets. True : la colonne Bucket_Anciennete s'ajoute aux colonnes utilisées
# (matrice, tableau, modèle). False : elle n'existe nulle part.
BUCKETS_ANCIENNETE = False
# Les bornes des buckets, en années : 1 = de 0 à 2 ans, 2 = de 2 à 5 ans, 3 = de 5 à 10 ans, puis un bucket
# tous les 5 ans : 4 = de 10 à 15 ans, ... 9 = 35 ans et plus. Pour d'autres buckets, changer les bornes.
BORNES_ANCIENNETE = [2, 5, 10, 15, 20, 25, 30, 35]


# ----------------------------------------------------------------------------------------------
# 4. LES MODÈLES
# ----------------------------------------------------------------------------------------------

# PROFONDEUR : le nombre de questions que l'arbre de décision peut enchaîner. Sans limite, il apprend
# le train par cœur et se trompe sur le test.
PROFONDEUR = 5

# LOG_SALAIRE. True : M1, M2 et M5 apprennent le logarithme du salaire (un écart se lit alors en pourcentage,
# et les très hauts salaires pèsent moins). False : ils apprennent le salaire tel quel.
LOG_SALAIRE = True

# LOG_COMPA_RATIO. True : M3, M4 et M6 apprennent le logarithme du Compa-Ratio (quelques Compa-Ratio très hauts
# pèsent alors moins sur le modèle). False : ils apprennent le Compa-Ratio tel quel.
LOG_COMPA_RATIO = True

# Les modèles du salaire reçoivent en plus le Mid : sans lui, ils ne connaissent pas la grille du poste.
# Les modèles du Compa-Ratio l'ont déjà, puisque le Compa-Ratio est le salaire divisé par le Mid.
# N'y mettre que des montants (Mid, Median...) : avec LOG_SALAIRE = True, ces colonnes passent elles aussi en logarithme.
# Liste vide : les six modèles ont exactement les mêmes colonnes.
EN_PLUS_POUR_LE_SALAIRE = ['Mid']

# PAQUETS : le nombre de paquets de la validation croisée.
PAQUETS = 5
