@echo off
rem Ouvre Fiabilisation_Diplomes_pas_a_pas_v12.ipynb dans le navigateur, avec le Python du venv du projet.
rem Il suffit de double-cliquer sur ce fichier.
rem Tout le travail (venv, bibliothèques, kernel « Python (.venv salaires) ») est fait par le
rem lancer_notebook.bat du dossier du projet, comme pour le notebook de l'EDA : on lui dit seulement quel notebook ouvrir.
call "%~dp0..\lancer_notebook.bat" "fiabilisation_diplomes\Fiabilisation_Diplomes_pas_a_pas_v12.ipynb"
