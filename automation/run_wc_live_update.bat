@echo off
REM Wrapper Planificateur de tâches : mise à jour Coupe du Monde légère (toutes les 2 h).
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
python "automation\wc_live_update.py" >> "automation\logs\wc_live_wrapper.log" 2>&1
