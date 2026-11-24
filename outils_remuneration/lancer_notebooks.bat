@echo off
chcp 65001 >nul
rem Ouvre ce dossier dans le navigateur, avec son propre Python (le venv du dossier).
rem Il suffit de double-cliquer sur ce fichier : il prépare tout ce qui manque, puis ouvre la page.
rem Dans la page, on clique sur le notebook à lancer (1_Visualisations, 2_Prediction ou
rem 3_Prediction_Par_Cohorte), ou sur reglages.py pour changer un réglage.
rem Ce dossier marche tout seul : ce fichier n'a besoin de rien en dehors de lui.
rem Pourquoi un .bat et pas un script PowerShell : sur beaucoup de PC d'entreprise, PowerShell refuse
rem de lancer des scripts (« l'exécution de scripts est désactivée ») ; un .bat, lui, se lance toujours.
rem Pourquoi chcp 65001 (ligne 2) : sans ça, la fenêtre noire affiche mal les accents des messages.

rem Se placer dans ce dossier, même si ce fichier est lancé depuis un autre endroit.
rem Pourquoi pushd et pas cd /d : quand le dossier est sur un dossier réseau (un chemin qui commence par
rem \\serveur\...), cd /d échoue et toute la suite tournerait ailleurs. pushd, lui, donne une lettre de
rem lecteur provisoire au dossier réseau (Z: par exemple) : la suite marche comme sur le disque du PC.
pushd "%~dp0" || goto :fin_erreur

rem Avant tout, la longueur du chemin du dossier (voir :verifier_longueur, tout en bas).
call :verifier_longueur || goto :fin_erreur

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
echo Vérification des bibliothèques...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :erreur_pip
rem    Pourquoi tester en plus : pip regarde seulement si une bibliothèque est notée comme installée, pas si
rem    tous ses fichiers sont là. Si une installation a été coupée en route, ou si l'antivirus a retiré des
rem    fichiers, pip ne voit rien et le programme s'arrête plus loin avec un message peu clair
rem    (« No module named ... »). Dans ce cas on refait le dossier .venv en entier, comme au premier lancement.
call :tester_bibliotheques && goto :bibliotheques_pretes
echo Des fichiers manquent dans les bibliothèques du dossier .venv : on le refait en entier.
echo Cela prend plusieurs minutes, comme au premier lancement.
rmdir /s /q .venv
call :creer_venv || goto :fin_erreur
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :erreur_pip
call :tester_bibliotheques || goto :erreur_bibliotheques
:bibliotheques_pretes

rem 3. Ouvrir le dossier dans le navigateur. Fermer cette fenêtre (ou Ctrl+C dedans) arrête Jupyter.
echo.
echo Le dossier s'ouvre dans le navigateur. Gardez cette fenêtre ouverte tant que vous l'utilisez.
".venv\Scripts\python.exe" -m notebook
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

:tester_bibliotheques
rem Deux contrôles, sans rien afficher. Renvoie une erreur dès que l'un des deux échoue.
rem a) Chaque bibliothèque garde la liste de ses fichiers : on regarde s'ils sont tous encore là.
rem    Les .pyc ne comptent pas : Python les refait tout seul quand ils manquent.
".venv\Scripts\python.exe" -c "import sys; from importlib.metadata import distributions; sys.exit(any(not f.locate().exists() for d in distributions() for f in (d.files or []) if f.suffix != '.pyc'))" >nul 2>&1 || exit /b 1
rem b) On charge pour de bon les bibliothèques demandées, comme le fera la suite.
".venv\Scripts\python.exe" -c "import numpy, pandas, sklearn.ensemble, yaml, joblib, openpyxl, plotly, statsmodels.api, ipykernel, notebook" >nul 2>&1 || exit /b 1
exit /b 0

:verifier_longueur
rem Pourquoi : certaines bibliothèques rangent leurs fichiers très profond. Le plus long fait 161 caractères
rem à partir de .venv (un fichier de jupyterlab, que Jupyter installe avec lui). Or, par défaut, Windows refuse
rem les chemins de plus de 259 caractères : ce dossier doit donc faire 98 caractères au plus.
rem Sans ce contrôle, l'installation échouerait au bout de plusieurs minutes, avec un message peu clair.
rem Si on change les versions de requirements.txt, ce 161 (et donc ce 98) peut changer.
rem Pas de limite quand le PC accepte les chemins longs (réglage LongPathsEnabled de Windows à 1).
reg query "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled 2>nul | findstr /c:"0x1" >nul && exit /b 0
rem Compter les caractères du chemin du dossier, barre finale comprise : on enlève une lettre à la fois.
set "RESTE=%CD%\"
set /a LONGUEUR=0
:compter_caracteres
if not defined RESTE goto :caracteres_comptes
set "RESTE=%RESTE:~1%"
set /a LONGUEUR+=1
goto :compter_caracteres
:caracteres_comptes
if %LONGUEUR% leq 98 exit /b 0
echo Ce dossier est rangé trop profond pour Windows :
echo   "%CD%"
echo Son chemin fait %LONGUEUR% caractères, il en faut 98 au plus : certaines bibliothèques ne pourraient pas s'installer.
echo Déplacez le dossier plus haut (par exemple directement dans Documents), puis relancez ce fichier.
exit /b 1

:erreur_bibliotheques
echo.
echo Les bibliothèques ne marchent toujours pas, même après avoir refait le dossier .venv.
echo Le plus souvent, c'est l'antivirus du PC qui retire ou bloque certains de leurs fichiers :
echo demandez à l'informatique d'autoriser ce dossier.
goto :fin_erreur

:erreur_pip
echo.
echo L'installation des bibliothèques a échoué : le message juste au-dessus dit pourquoi.
echo Sur un PC d'entreprise, c'est souvent le réseau qui bloque l'accès à pypi.org : demandez à l'informatique.

:fin_erreur
echo.
pause
exit /b 1
