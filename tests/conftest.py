# -*- coding: utf-8 -*-
"""
Fichier technique lu automatiquement par pytest avant de lancer les tests.

A quoi ca sert : le code a tester (anomaly_core.py) se trouve dans le dossier src/, pas dans
tests/. Ce petit fichier indique a Python ou aller chercher anomaly_core.py, pour que chaque
fichier de test puisse simplement ecrire "from anomaly_core import ...", peu importe l'endroit
d'ou la commande pytest est lancee.

Vous n'avez rien a modifier ici pour ajouter ou lancer des tests.
"""

import sys
from pathlib import Path

CODES_DIR = Path(__file__).resolve().parent.parent / "src"
if str(CODES_DIR) not in sys.path:
    sys.path.insert(0, str(CODES_DIR))
