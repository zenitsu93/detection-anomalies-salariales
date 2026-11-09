@echo off
chcp 65001 >nul
rem Ouvre Fiabilisation_Diplomes_pas_a_pas_v13.ipynb dans le navigateur, avec le Python du venv du projet.
rem Il suffit de double-cliquer sur ce fichier.
rem Tout le travail (venv, bibliothèques, kernel « Python (.venv salaires) ») est fait par le
rem lancer_notebook.bat du dossier du projet, comme pour le notebook de l'EDA : on lui dit seulement quel notebook ouvrir.
rem Pourquoi chcp 65001 (ligne 2) : pour que le message d'erreur du bas s'affiche avec ses accents.

rem Pourquoi vérifier que celui du projet est là : il manque si ce dossier a été copié seul, ou si ce fichier
rem a été lancé directement depuis le zip téléchargé, sans l'extraire. La fenêtre se fermerait alors
rem aussitôt, sans rien expliquer.
if not exist "%~dp0..\lancer_notebook.bat" goto :projet_incomplet
call "%~dp0..\lancer_notebook.bat" "fiabilisation_diplomes\Fiabilisation_Diplomes_pas_a_pas_v13.ipynb"
exit /b

:projet_incomplet
echo Le fichier lancer_notebook.bat du dossier du projet est introuvable.
echo Ce notebook a besoin de tout le projet : si vous l'avez téléchargé depuis GitHub, faites un clic droit
echo sur le zip, puis « Extraire tout », et relancez ce fichier depuis le dossier extrait.
pause
exit /b 1
