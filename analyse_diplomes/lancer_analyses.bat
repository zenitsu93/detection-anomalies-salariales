@echo off
chcp 65001 >nul
rem Lance les trois analyses du diplôme (groupes de collègues, IA, régression), puis ouvre le dossier où
rem arrivent leurs pages. Il suffit de double-cliquer sur ce fichier.
rem Ces analyses ne changent pas la détection : elles la comparent, sans puis avec le diplôme.
rem Pourquoi chcp 65001 (ligne 2) : sans ça, la fenêtre noire affiche mal les accents des messages.

rem Se placer dans le dossier du projet (un cran au-dessus de ce fichier), même lancé depuis un autre
rem dossier. Pourquoi pushd : il marche aussi sur un dossier réseau (\serveur\...), comme lancer_notebook.bat.
pushd "%~dp0.." || goto :fin

rem Le Python du projet est celui du dossier .venv, que lancer_notebook.bat (à la racine du projet) crée et
rem remplit la première fois. Pourquoi ne pas le recréer ici : ce serait recopier tout ce que fait déjà
rem lancer_notebook.bat ; il suffit de le lancer une fois.
if not exist ".venv\Scripts\python.exe" (
    echo Le Python du projet n'est pas encore installé.
    echo Double-cliquer une fois sur lancer_notebook.bat, à la racine du projet, puis relancer ce fichier.
    goto :fin
)
rem Pourquoi PYTHONIOENCODING : pour que les messages de Python gardent leurs accents dans la fenêtre.
set "PYTHONIOENCODING=utf-8"

echo 1/3 - Le diplôme dans les groupes de collègues...
".venv\Scripts\python.exe" analyse_diplomes\cohortes.py || goto :fin
echo.
echo 2/3 - Le diplôme dans l'IA...
".venv\Scripts\python.exe" analyse_diplomes\ia.py || goto :fin
echo.
echo 3/3 - Le diplôme dans la régression...
".venv\Scripts\python.exe" analyse_diplomes\regression.py || goto :fin
echo.
echo Terminé. Les pages s'ouvrent avec un navigateur : la plus récente de chaque analyse est la dernière de la liste.
start "" "output\analyse_diplomes"

:fin
rem La fenêtre reste ouverte jusqu'à ce qu'on appuie sur une touche, pour laisser le temps de lire.
pause
popd
