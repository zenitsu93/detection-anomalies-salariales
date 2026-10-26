@echo off
chcp 65001 >nul
rem Ouvre notebooks\EDA_Positionnement_Salarial_Comite.ipynb dans le navigateur, avec le Python du venv du projet.
rem Un autre .bat peut lui demander d'ouvrir un autre notebook, en donnant son chemin à la suite :
rem c'est ce que fait fiabilisation_diplomes\lancer_notebook.bat, pour ne pas recopier tout ce qui suit.
rem Il suffit de double-cliquer sur ce fichier : il prépare tout ce qui manque, puis ouvre le notebook.
rem Pourquoi un .bat et pas un script PowerShell : sur beaucoup de PC d'entreprise, PowerShell refuse
rem de lancer des scripts (« l'exécution de scripts est désactivée ») ; un .bat, lui, se lance toujours.
rem Pourquoi chcp 65001 (ligne 2) : sans ça, la fenêtre noire affiche mal les accents des messages.

rem Se placer dans le dossier du projet, même si ce fichier est lancé depuis un autre dossier.
cd /d "%~dp0"

rem 1. Le venv. Un venv copié depuis un autre PC ne marche pas : il cherche le Python de l'autre PC.
rem    Dans ce cas on le supprime pour le refaire : il ne contient que des bibliothèques qu'on réinstalle.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1 || (
        echo Le dossier .venv vient d'un autre PC et ne marche pas ici : on le refait.
        rmdir /s /q .venv
    )
)
if not exist ".venv\Scripts\python.exe" call :creer_venv || goto :fin_erreur

rem 2. Les bibliothèques. La première fois, tout s'installe (quelques minutes) ;
rem    les fois suivantes, pip voit que tout est déjà là et passe en quelques secondes.
echo Vérification des bibliothèques du notebook...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements-notebook.txt || goto :erreur_pip

rem 3. Le kernel. On présente le Python du venv à Jupyter sous le nom « Python (.venv salaires) ».
rem    Le notebook demande ce kernel-là : il s'ouvre donc directement avec le bon Python, sans rien choisir.
rem    --sys-prefix range cette déclaration dans .venv : rien n'est écrit ailleurs sur le PC.
".venv\Scripts\python.exe" -m ipykernel install --sys-prefix --name salaires-venv --display-name "Python (.venv salaires)" >nul || goto :fin_erreur

rem 4. Ouvrir le notebook dans le navigateur. Fermer cette fenêtre (ou Ctrl+C dedans) arrête Jupyter.
rem    Le notebook demandé par un autre .bat (voir en tête) ; sinon, celui de l'EDA.
set "NOTEBOOK=%~1"
if not defined NOTEBOOK set "NOTEBOOK=notebooks\EDA_Positionnement_Salarial_Comite.ipynb"
echo.
echo Le notebook s'ouvre dans le navigateur. Gardez cette fenêtre ouverte tant que vous l'utilisez.
".venv\Scripts\python.exe" -m notebook "%NOTEBOOK%"
exit /b 0


:creer_venv
rem Pourquoi Python 3.10 à 3.13 : les versions de bibliothèques fixées dans requirements.txt
rem n'existent toutes que pour ces versions de Python. On prend la plus récente qui est installée.
set "PYBASE="
for %%v in (3.13 3.12 3.11 3.10) do if not defined PYBASE py -%%v -c "import sys" >nul 2>&1 && set "PYBASE=py -%%v"
rem Pas de lanceur « py » sur ce PC : on essaie le « python » de base, s'il a la bonne version.
if not defined PYBASE python -c "import sys; sys.exit(not (3, 10) <= sys.version_info[:2] <= (3, 13))" >nul 2>&1 && set "PYBASE=python"
if not defined PYBASE (
    echo Aucun Python 3.10 à 3.13 trouvé sur ce PC.
    echo Installez-en un depuis python.org, ou demandez-le à l'informatique, puis relancez ce fichier.
    exit /b 1
)
echo Création du venv avec %PYBASE%...
%PYBASE% -m venv .venv || exit /b 1
exit /b 0

:erreur_pip
echo.
echo L'installation des bibliothèques a échoué : le message juste au-dessus dit pourquoi.
echo Sur un PC d'entreprise, c'est souvent le réseau qui bloque l'accès à pypi.org : demandez à l'informatique.

:fin_erreur
echo.
pause
exit /b 1
