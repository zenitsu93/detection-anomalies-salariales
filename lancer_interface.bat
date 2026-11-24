@echo off
chcp 65001 >nul
rem Lance toute l'interface d'un double-clic : la détection, puis l'écran d'accueil avec ses trois outils
rem (explorer les données, détecter les anomalies, décider d'un salaire).
rem Il suffit de double-cliquer sur ce fichier : il prépare tout ce qui manque, refait la détection sur
rem les fichiers de input\, puis ouvre accueil.html dans le navigateur.
rem Pourquoi un .bat et pas un script PowerShell : sur beaucoup de PC d'entreprise, PowerShell refuse
rem de lancer des scripts (« l'exécution de scripts est désactivée ») ; un .bat, lui, se lance toujours.
rem Pourquoi chcp 65001 (ligne 2) : sans ça, la fenêtre noire affiche mal les accents des messages.

rem Se placer dans le dossier du projet, même si ce fichier est lancé depuis un autre dossier.
rem Pourquoi pushd et pas cd /d : quand le projet est sur un dossier réseau (un chemin qui commence par
rem \\serveur\...), cd /d échoue et toute la suite tournerait dans un autre dossier, sans le projet.
rem pushd, lui, donne une lettre de lecteur provisoire au dossier réseau (Z: par exemple) : la suite marche
rem comme sur le disque du PC. Sur un dossier du PC, pushd fait exactement la même chose que cd /d.
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

rem 3. La détection. Elle relit les fichiers de input\ et refait les résultats, le tableau de bord et
rem    l'écran d'accueil. Pourquoi la refaire à chaque lancement : les trois outils montrent ainsi toujours
rem    les données qui sont dans input\ en ce moment, même si on vient de les remplacer.
rem    Chaque lancement ajoute un tableau de bord dans output\dashboard\ ; l'écran d'accueil ouvre le dernier.
echo.
echo Détection des anomalies...
".venv\Scripts\python.exe" src\detect_salary_anomalies.py || goto :erreur_detection

rem 4. Le programme de l'interface (decision_support\app.py). Il fait tourner l'aide à la décision, et il
rem    sert aussi l'écran d'accueil, l'exploration et le tableau de bord à l'adresse http://127.0.0.1:8765 :
rem    c'est ce qui permet au bouton « Refaire la détection » du tableau de bord de marcher.
rem    --ouvrir accueil.html : dès que le programme est prêt, il ouvre l'écran d'accueil dans le navigateur.
rem    Fermer cette fenêtre (ou Ctrl+C dedans) arrête l'interface : les pages ouvertes ne répondent plus.
rem    Sans cette fenêtre, accueil.html s'ouvre encore d'un double-clic ; seuls l'aide à la décision et le
rem    bouton « Refaire la détection » ne marchent pas.
echo.
echo L'écran d'accueil s'ouvre dans le navigateur. Gardez cette fenêtre ouverte tant que vous l'utilisez.
".venv\Scripts\python.exe" -m decision_support.app --ouvrir accueil.html || goto :erreur_aide_decision
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
".venv\Scripts\python.exe" -c "import numpy, pandas, sklearn.ensemble, yaml, joblib, openpyxl" >nul 2>&1 || exit /b 1
exit /b 0

:verifier_longueur
rem Pourquoi : certaines bibliothèques rangent leurs fichiers très profond. Le plus long fait 125 caractères
rem à partir de .venv (un fichier de scikit-learn). Or, par défaut, Windows refuse les chemins de plus de
rem 259 caractères : le dossier du projet doit donc faire 134 caractères au plus.
rem Cette limite est plus large que celle de lancer_notebook.bat (98), qui installe en plus Jupyter.
rem Sans ce contrôle, l'installation échouerait au bout de plusieurs minutes, avec un message peu clair.
rem Si on change les versions de requirements.txt, ce 125 (et donc ce 134) peut changer.
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
if %LONGUEUR% leq 134 exit /b 0
echo Le dossier du projet est rangé trop profond pour Windows :
echo   "%CD%"
echo Son chemin fait %LONGUEUR% caractères, il en faut 134 au plus : certaines bibliothèques ne pourraient pas s'installer.
echo Déplacez le dossier plus haut (par exemple directement dans Documents), puis relancez ce fichier.
exit /b 1

:erreur_detection
echo.
echo La détection s'est arrêtée : le message juste au-dessus dit pourquoi.
rem On ne parle des fichiers de input\ que si c'est bien eux : on regarde lequel manque.
rem (Les bibliothèques, elles, ont déjà été testées à l'étape 2.)
set "MANQUE="
for %%f in (employes.xlsx bands.xlsx market.xlsx) do if not exist "input\%%f" (
    echo Il manque le fichier input\%%f.
    set "MANQUE=1"
)
if not defined MANQUE echo S'il parle de « Permission denied », un fichier de input\ ou de output\ est resté ouvert dans Excel : fermez-le, puis relancez ce fichier.
goto :fin_erreur

:erreur_aide_decision
echo.
echo L'interface n'a pas démarré : le message juste au-dessus dit pourquoi.
echo Si elle tourne déjà dans une autre fenêtre noire, fermez cette autre fenêtre puis relancez ce fichier.
goto :fin_erreur

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
