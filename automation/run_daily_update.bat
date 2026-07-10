@echo off
REM Wrapper pour le Planificateur de tâches Windows : lance la mise à jour quotidienne
REM complète (prédictions clubs + Coupe du Monde + autres championnats) puis pousse.
cd /d "%~dp0.."
python "automation\daily_update.py" >> "automation\logs\task_wrapper.log" 2>&1
